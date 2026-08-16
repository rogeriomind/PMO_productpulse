import logging
import time

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.clients.agent_api_client import (
    AgentApiClient,
    AgentApiContractError,
    AgentApiError,
)
from app.config import Settings, get_settings
from app.contracts.agent_response import AgentResponse
from app.database.connection import MessageRecord, session_scope
from app.integrations.agent_event_mapper import AgentEventMapper
from app.logging_config import configure_logging
from app.providers.mock_transcription_provider import MockTranscriptionProvider
from app.providers.telegram_provider import TelegramMessageProvider
from app.providers.whatsapp_provider_mock import WhatsAppMessageProviderMock
from app.renderers.channel_response_renderer import ChannelResponseRenderer
from app.repositories.agent_dispatch_repository import AgentDispatchRepository
from app.repositories.audit_repository import AuditRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.debounce_repository import DebounceRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.services.agent_dispatch_service import AgentDispatchService
from app.services.audit_service import AuditService
from app.services.debounce_service import DebounceService
from app.services.outbound_service import OutboundService
from app.services.preprocessing_service import PreprocessingService
from app.services.queue_service import QueueService

logger = logging.getLogger(__name__)


class WorkerProcessingError(RuntimeError):
    def __init__(
        self, message: str, *, dispatch_id: str | None = None, phase: str = "processing"
    ):
        super().__init__(message)
        self.dispatch_id = dispatch_id
        self.phase = phase


class MessageWorker:
    def __init__(
        self,
        db: Session,
        settings: Settings | None = None,
        agent_api_client: AgentApiClient | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()

        self.audit_service = AuditService(AuditRepository(db))
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)
        self.queue_repository = QueueRepository(db)
        self.queue_service = QueueService(
            self.queue_repository,
            lock_seconds=self.settings.queue_lock_seconds,
            max_attempts=self.settings.max_queue_attempts,
        )
        self.preprocessing_service = PreprocessingService(
            MockTranscriptionProvider(), self.audit_service
        )
        self.debounce_service = DebounceService(
            DebounceRepository(db),
            self.message_repository,
            self.queue_repository,
            self.audit_service,
            self.settings.debounce_seconds,
        )
        self.outbound_service = OutboundService(
            self.message_repository,
            self.audit_service,
            {
                "telegram": TelegramMessageProvider(self.settings),
                "whatsapp": WhatsAppMessageProviderMock(),
            },
        )
        self.agent_api_client = agent_api_client or AgentApiClient(self.settings)
        self.agent_event_mapper = AgentEventMapper(self.settings)
        self.agent_dispatch_service = AgentDispatchService(
            AgentDispatchRepository(db), self.audit_service
        )
        self.response_renderer = ChannelResponseRenderer()

    def process_once(self) -> dict:
        self.audit_service.record("worker_started", "started")
        queue_item = self.queue_service.lock_next()
        if not queue_item:
            return {"processed": False, "reason": "no_message"}

        self.audit_service.record(
            "queue_locked",
            "success",
            conversation_id=queue_item.conversation_id,
            message_id=queue_item.message_id,
            payload={"queue_id": queue_item.id, "attempts": queue_item.attempts},
        )

        conversation = self.conversation_repository.get(queue_item.conversation_id)
        message = self.message_repository.get(queue_item.message_id)
        if not conversation or not message:
            self.queue_service.mark_failed(
                queue_item.id, "Mensagem ou conversa não encontrada"
            )
            return {"processed": False, "reason": "missing_records"}

        try:
            return self._handle_message(conversation, message, queue_item.id)
        except WorkerProcessingError as exc:
            result = self.queue_service.retry_or_fail(queue_item.id, str(exc))
            if exc.dispatch_id:
                if result == "failed":
                    self.agent_dispatch_service.mark_failed(exc.dispatch_id, str(exc))
                    if exc.phase == "agent":
                        self._send_technical_fallback(conversation)
                elif exc.phase == "delivery":
                    self.agent_dispatch_service.mark_delivery_failed(
                        exc.dispatch_id, str(exc)
                    )
                else:
                    self.agent_dispatch_service.mark_retry(exc.dispatch_id, str(exc))
            self.audit_service.record(
                "queue_failed" if result == "failed" else "queue_retry",
                result,
                conversation_id=conversation.id,
                message_id=message.id,
                payload={
                    "queue_id": queue_item.id,
                    "phase": exc.phase,
                    "dispatch_id": exc.dispatch_id,
                },
                error_message=str(exc),
            )
            return {
                "processed": False,
                "reason": result,
                "error": str(exc),
                "queue_id": queue_item.id,
            }
        except Exception as exc:
            result = self.queue_service.retry_or_fail(
                queue_item.id, "Erro técnico no worker."
            )
            self.audit_service.record(
                "queue_failed" if result == "failed" else "queue_retry",
                result,
                conversation_id=conversation.id,
                message_id=message.id,
                payload={"queue_id": queue_item.id},
                error_message=str(exc),
            )
            return {
                "processed": False,
                "reason": result,
                "error": "Erro técnico no worker.",
                "queue_id": queue_item.id,
            }

    def _handle_message(
        self, conversation, message: MessageRecord, queue_id: str
    ) -> dict:
        if self._should_debounce(message):
            decision = self.debounce_service.assess_text(conversation.id, message.id)
            if decision.should_wait:
                self.queue_service.postpone(
                    queue_id, "debounce_waiting", decision.remaining_seconds
                )
                return {"processed": False, "reason": "deferred", "queue_id": queue_id}

            processed_text = self.preprocessing_service.process(
                message, override_text=decision.combined_text
            )
            event_id = (
                self.agent_event_mapper.debounce_event_id(
                    conversation.provider,
                    conversation.id,
                    decision.message_ids,
                    decision.combined_text,
                )
                if len(decision.message_ids) > 1
                else message.event_id
            )
            return self._process_agent_event(
                conversation,
                message,
                processed_text,
                queue_ids=decision.queue_ids or [queue_id],
                source_message_ids=decision.message_ids or [message.id],
                event_id=event_id,
                transcribed=False,
            )

        processed_text = (
            None
            if message.callback_data
            else self.preprocessing_service.process(message)
        )
        return self._process_agent_event(
            conversation,
            message,
            processed_text,
            queue_ids=[queue_id],
            source_message_ids=[message.id],
            event_id=message.event_id,
            transcribed=message.content_type == "audio",
        )

    def _process_agent_event(
        self,
        conversation,
        message: MessageRecord,
        processed_text: str | None,
        *,
        queue_ids: list[str],
        source_message_ids: list[str],
        event_id: str | None,
        transcribed: bool,
    ) -> dict:
        agent_event = self.agent_event_mapper.map(
            conversation,
            message,
            processed_text,
            event_id=event_id,
            source_message_ids=source_message_ids,
            transcribed=transcribed,
        )
        self.audit_service.record(
            "agent_event_built",
            "success",
            conversation_id=conversation.id,
            message_id=message.id,
            payload={
                "event_id": agent_event.event_id,
                "request_id": agent_event.request_id,
                "correlation_id": agent_event.correlation_id,
                "thread_id": agent_event.thread_id,
                "channel": agent_event.channel,
                "agent_event_type": agent_event.message_type,
            },
        )

        dispatch = self.agent_dispatch_service.get_or_create(
            conversation.id, agent_event
        )
        if dispatch.status == "delivered":
            self.queue_service.mark_done_many(queue_ids)
            return {
                "processed": True,
                "reason": "already_delivered",
                "dispatch_id": dispatch.id,
            }

        if dispatch.response_payload:
            try:
                agent_response = AgentResponse.model_validate(dispatch.response_payload)
            except ValidationError as exc:
                raise WorkerProcessingError(
                    "Resposta persistida da API da IA não respeita o contrato.",
                    dispatch_id=dispatch.id,
                    phase="render",
                ) from exc
        else:
            agent_response = self._call_agent(
                dispatch.id, conversation.id, message.id, agent_event
            )
            dispatch = self.agent_dispatch_service.save_response(
                dispatch, agent_response
            )

        outbound = self._render_response(
            dispatch.id,
            conversation.id,
            message.id,
            conversation.provider,
            agent_response,
        )
        self._deliver_response(dispatch.id, conversation, outbound)
        self.queue_service.mark_done_many(queue_ids)
        self.audit_service.record(
            "queue_done",
            "success",
            conversation_id=conversation.id,
            message_id=message.id,
            payload={"queue_ids": queue_ids, "dispatch_id": dispatch.id},
        )
        return {"processed": True, "dispatch_id": dispatch.id, "queue_ids": queue_ids}

    def _call_agent(
        self, dispatch_id: str, conversation_id: str, message_id: str, agent_event
    ) -> AgentResponse:
        self.agent_dispatch_service.mark_calling(dispatch_id)
        self.audit_service.record(
            "agent_api_call_started",
            "started",
            conversation_id=conversation_id,
            message_id=message_id,
            payload={
                "dispatch_id": dispatch_id,
                "event_id": agent_event.event_id,
                "request_id": agent_event.request_id,
                "correlation_id": agent_event.correlation_id,
                "thread_id": agent_event.thread_id,
                "agent_event_type": agent_event.message_type,
            },
        )
        started = time.monotonic()
        try:
            response = self.agent_api_client.send_event(agent_event)
        except AgentApiError as exc:
            self.audit_service.record(
                "agent_api_call_failed",
                "failed",
                conversation_id=conversation_id,
                message_id=message_id,
                payload={
                    "dispatch_id": dispatch_id,
                    "event_id": agent_event.event_id,
                    "status_code": exc.status_code,
                },
                error_message=str(exc),
            )
            raise WorkerProcessingError(
                str(exc), dispatch_id=dispatch_id, phase="agent"
            ) from exc

        latency_ms = int((time.monotonic() - started) * 1000)
        self.audit_service.record(
            "agent_api_call_succeeded",
            "success",
            conversation_id=conversation_id,
            message_id=message_id,
            payload={
                "dispatch_id": dispatch_id,
                "event_id": agent_event.event_id,
                "agent_status": response.status,
                "latency_ms": latency_ms,
            },
        )
        return response

    def _render_response(
        self,
        dispatch_id: str,
        conversation_id: str,
        message_id: str,
        channel: str,
        agent_response: AgentResponse,
    ):
        self.audit_service.record(
            "channel_render_started",
            "started",
            conversation_id=conversation_id,
            message_id=message_id,
            payload={
                "dispatch_id": dispatch_id,
                "channel": channel,
                "agent_status": agent_response.status,
            },
        )
        try:
            outbound = self.response_renderer.render(
                channel=channel, agent_response=agent_response
            )
        except AgentApiContractError as exc:
            self.audit_service.record(
                "channel_render_failed",
                "failed",
                conversation_id=conversation_id,
                message_id=message_id,
                payload={"dispatch_id": dispatch_id, "channel": channel},
                error_message=str(exc),
            )
            raise WorkerProcessingError(
                str(exc), dispatch_id=dispatch_id, phase="render"
            ) from exc
        self.audit_service.record(
            "channel_render_succeeded",
            "success",
            conversation_id=conversation_id,
            message_id=message_id,
            payload={"dispatch_id": dispatch_id, "channel": channel},
        )
        return outbound

    def _deliver_response(self, dispatch_id: str, conversation, outbound) -> None:
        self.agent_dispatch_service.mark_delivering(dispatch_id)
        self.audit_service.record(
            "agent_delivery_started",
            "started",
            conversation_id=conversation.id,
            payload={"dispatch_id": dispatch_id, "channel": conversation.provider},
        )
        try:
            self.outbound_service.send(conversation, outbound)
        except Exception as exc:
            self.agent_dispatch_service.mark_delivery_failed(dispatch_id, str(exc))
            self.audit_service.record(
                "agent_delivery_failed",
                "failed",
                conversation_id=conversation.id,
                payload={"dispatch_id": dispatch_id, "channel": conversation.provider},
                error_message=str(exc),
            )
            raise WorkerProcessingError(
                str(exc), dispatch_id=dispatch_id, phase="delivery"
            ) from exc
        self.agent_dispatch_service.mark_delivered(dispatch_id)
        self.audit_service.record(
            "agent_delivery_succeeded",
            "success",
            conversation_id=conversation.id,
            payload={"dispatch_id": dispatch_id, "channel": conversation.provider},
        )

    def _should_debounce(self, message: MessageRecord) -> bool:
        text = (message.normalized_text or "").strip()
        return (
            message.content_type == "text"
            and not message.callback_data
            and not text.startswith("/start")
        )

    def _send_technical_fallback(self, conversation) -> None:
        try:
            self.outbound_service.send_text(
                conversation, self.settings.agent_technical_fallback_message
            )
        except Exception as exc:
            self.audit_service.record(
                "agent_delivery_failed",
                "failed",
                conversation_id=conversation.id,
                payload={"technical_fallback": True},
                error_message=str(exc),
            )


def run_forever() -> None:
    configure_logging()
    settings = get_settings()
    while True:
        with session_scope() as db:
            worker = MessageWorker(db, settings)
            result = worker.process_once()
            logger.info("worker_tick", extra={"payload": result})
        time.sleep(settings.worker_sleep_seconds)


if __name__ == "__main__":
    run_forever()
