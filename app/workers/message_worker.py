import logging
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime

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
from app.workers.queue_listener import QueueListener
from app.workers.runtime import WorkerRuntime

logger = logging.getLogger(__name__)

NON_SUPPRESSIBLE_STATUSES = {"awaiting_confirmation", "completed", "cancelled"}


@dataclass
class PollingBackoff:
    base_seconds: float
    max_seconds: float

    def __post_init__(self) -> None:
        self.current_seconds = self.base_seconds

    def next_empty_sleep(self) -> float:
        sleep_seconds = self.current_seconds
        self.current_seconds = min(self.current_seconds * 2, self.max_seconds)
        return sleep_seconds

    def reset(self) -> None:
        self.current_seconds = self.base_seconds


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
        agent_event_mapper: AgentEventMapper | None = None,
        response_renderer: ChannelResponseRenderer | None = None,
        telegram_provider: TelegramMessageProvider | None = None,
        whatsapp_provider: WhatsAppMessageProviderMock | None = None,
        transcription_provider: MockTranscriptionProvider | None = None,
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
            transcription_provider or MockTranscriptionProvider(), self.audit_service
        )
        self.debounce_service = DebounceService(
            DebounceRepository(db),
            self.message_repository,
            self.queue_repository,
            self.audit_service,
            self.settings.debounce_seconds,
            self.settings.debounce_max_seconds,
            adaptive_enabled=self.settings.debounce_adaptive_enabled,
            debounce_min_seconds=self.settings.debounce_min_ms / 1000,
            debounce_increment_seconds=self.settings.debounce_increment_ms / 1000,
            debounce_max_messages=self.settings.debounce_max_messages,
            adaptive_max_seconds=self.settings.debounce_max_ms / 1000,
        )
        telegram_provider = telegram_provider or TelegramMessageProvider(self.settings)
        whatsapp_provider = whatsapp_provider or WhatsAppMessageProviderMock()
        self.outbound_service = OutboundService(
            self.message_repository,
            self.audit_service,
            {
                "telegram": telegram_provider,
                "whatsapp": whatsapp_provider,
            },
        )
        self.agent_api_client = agent_api_client or AgentApiClient(self.settings)
        self.agent_event_mapper = agent_event_mapper or AgentEventMapper(self.settings)
        self.agent_dispatch_repository = AgentDispatchRepository(db)
        self.agent_dispatch_service = AgentDispatchService(
            self.agent_dispatch_repository, self.audit_service
        )
        self.response_renderer = response_renderer or ChannelResponseRenderer()

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
            payload={
                "queue_id": queue_item.id,
                "attempts": queue_item.attempts,
                "queue_created_at": queue_item.created_at.isoformat(),
                "queue_locked_at": self._isoformat(queue_item.queue_locked_at),
                "queue_wait_ms": self._duration_ms(
                    queue_item.created_at, queue_item.queue_locked_at
                ),
            },
        )

        conversation = self.conversation_repository.get(queue_item.conversation_id)
        message = self.message_repository.get(queue_item.message_id)
        if not conversation or not message:
            self.queue_service.mark_failed(
                queue_item.id, "Mensagem ou conversa não encontrada"
            )
            return {"processed": False, "reason": "missing_records"}

        self._send_typing_indicator(conversation)
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
        bypass_reason = self._debounce_bypass_reason(conversation, message)
        if not bypass_reason:
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

        self._record_debounce_bypass(conversation, message, queue_id, bypass_reason)
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
        if dispatch.status in {"delivered", "superseded"}:
            self.queue_service.mark_done_many(queue_ids)
            return {
                "processed": True,
                "reason": "already_delivered"
                if dispatch.status == "delivered"
                else "already_superseded",
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
            self._send_typing_indicator(conversation)
            self.queue_service.mark_ia_request_started_many(queue_ids)
            agent_response = self._call_agent(
                dispatch.id, conversation.id, message.id, agent_event
            )
            self.queue_service.mark_ia_response_received_many(queue_ids)
            dispatch = self.agent_dispatch_service.save_response(
                dispatch, agent_response
            )

        if self._should_suppress_response(
            conversation.id,
            source_message_ids,
            agent_event.message_type,
            agent_response,
        ):
            self.agent_dispatch_service.mark_superseded(dispatch.id)
            self.queue_service.mark_done_many(queue_ids)
            self.audit_service.record(
                "queue_done",
                "success",
                conversation_id=conversation.id,
                message_id=message.id,
                payload={
                    "queue_ids": queue_ids,
                    "dispatch_id": dispatch.id,
                    "suppressed": True,
                },
            )
            return {
                "processed": True,
                "reason": "superseded",
                "dispatch_id": dispatch.id,
                "queue_ids": queue_ids,
            }

        outbound = self._render_response(
            dispatch.id,
            conversation.id,
            message.id,
            conversation.provider,
            agent_response,
        )
        self._deliver_response(dispatch.id, conversation, outbound, agent_response)
        self.queue_service.mark_response_sent_many(queue_ids)
        self.queue_service.mark_done_many(queue_ids)
        self._record_latency_metrics(
            conversation,
            message,
            queue_ids,
            source_message_ids,
            agent_event,
            dispatch.id,
        )
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

    def _deliver_response(
        self, dispatch_id: str, conversation, outbound, agent_response: AgentResponse
    ) -> None:
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
        if agent_response.ui.context_id:
            self.conversation_repository.set_last_delivered_ui_context_id(
                conversation.id, agent_response.ui.context_id
            )
        self.audit_service.record(
            "agent_delivery_succeeded",
            "success",
            conversation_id=conversation.id,
            payload={"dispatch_id": dispatch_id, "channel": conversation.provider},
        )

    def _debounce_bypass_reason(
        self, conversation, message: MessageRecord
    ) -> str | None:
        text = (message.normalized_text or "").strip()
        if message.callback_data:
            return "callback"
        if message.message_type in {"callback", "confirmation"}:
            return message.message_type
        if message.content_type != "text":
            return "non_text"
        if self._is_immediate_text_command(text):
            return "command"
        if self._is_pending_confirmation_reply(conversation.id, text):
            return "pending_confirmation"
        return None

    def _is_immediate_text_command(self, text: str) -> bool:
        normalized = text.strip().lower()
        return normalized.startswith(("/", "menu:", "confirmation:", "global:"))

    def _is_pending_confirmation_reply(self, conversation_id: str, text: str) -> bool:
        normalized = text.strip().lower()
        confirmation_terms = {
            "sim",
            "s",
            "yes",
            "y",
            "não",
            "nao",
            "n",
            "no",
            "confirmo",
            "confirma",
            "pode fazer",
            "cancela",
            "cancelar",
        }
        if normalized not in confirmation_terms:
            return False

        dispatch = self.agent_dispatch_repository.latest_by_conversation(
            conversation_id
        )
        if not dispatch or not dispatch.response_payload:
            return False

        response_payload = dispatch.response_payload
        return bool(
            response_payload.get("requires_confirmation")
            or response_payload.get("status") == "awaiting_confirmation"
            or (response_payload.get("ui") or {}).get("type") == "confirmation"
        )

    def _record_debounce_bypass(
        self,
        conversation,
        message: MessageRecord,
        queue_id: str,
        reason: str,
    ) -> None:
        self.audit_service.record(
            "debounce_bypassed",
            "success",
            conversation_id=conversation.id,
            message_id=message.id,
            payload={"queue_id": queue_id, "reason": reason},
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

    def _should_suppress_response(
        self,
        conversation_id: str,
        source_message_ids: list[str],
        message_type: str,
        agent_response: AgentResponse,
    ) -> bool:
        if message_type == "confirmation":
            return False
        if agent_response.status in NON_SUPPRESSIBLE_STATUSES:
            return False
        if agent_response.requires_confirmation or agent_response.confirmation:
            return False
        return self.message_repository.has_newer_inbound(
            conversation_id, source_message_ids
        )

    def _send_typing_indicator(self, conversation) -> None:
        self.outbound_service.send_typing(conversation)

    def _record_latency_metrics(
        self,
        conversation,
        message: MessageRecord,
        queue_ids: list[str],
        source_message_ids: list[str],
        agent_event,
        dispatch_id: str,
    ) -> None:
        queues = self.queue_repository.list_by_ids(queue_ids)
        source_messages = [
            source_message
            for source_message_id in source_message_ids
            if (source_message := self.message_repository.get(source_message_id))
        ]
        if not queues:
            return

        message_received_at = min(
            (source_message.created_at for source_message in source_messages),
            default=message.created_at,
        )
        queue_created_at = min(queue.created_at for queue in queues)
        queue_locked_at = self._min_datetime(queue.queue_locked_at for queue in queues)
        debounce_started_at = self._min_datetime(
            queue.debounce_started_at for queue in queues
        )
        debounce_finished_at = self._max_datetime(
            queue.debounce_finished_at for queue in queues
        )
        ia_request_started_at = self._min_datetime(
            queue.ia_request_started_at for queue in queues
        )
        ia_response_received_at = self._max_datetime(
            queue.ia_response_received_at for queue in queues
        )
        response_sent_at = self._max_datetime(
            queue.response_sent_at for queue in queues
        )

        payload = {
            "request_id": agent_event.request_id,
            "correlation_id": agent_event.correlation_id,
            "conversation_id": conversation.id,
            "thread_id": agent_event.thread_id,
            "message_id": message.id,
            "source_message_ids": source_message_ids,
            "queue_ids": queue_ids,
            "dispatch_id": dispatch_id,
            "event_id": agent_event.event_id,
            "message_received_at": self._isoformat(message_received_at),
            "queue_created_at": self._isoformat(queue_created_at),
            "queue_locked_at": self._isoformat(queue_locked_at),
            "debounce_started_at": self._isoformat(debounce_started_at),
            "debounce_finished_at": self._isoformat(debounce_finished_at),
            "ia_request_started_at": self._isoformat(ia_request_started_at),
            "ia_response_received_at": self._isoformat(ia_response_received_at),
            "response_sent_at": self._isoformat(response_sent_at),
            "queue_wait_ms": self._duration_ms(queue_created_at, queue_locked_at),
            "debounce_wait_ms": self._duration_ms(
                debounce_started_at, debounce_finished_at
            ),
            "ia_http_latency_ms": self._duration_ms(
                ia_request_started_at, ia_response_received_at
            ),
            "outbound_latency_ms": self._duration_ms(
                ia_response_received_at, response_sent_at
            ),
            "total_latency_ms": self._duration_ms(
                message_received_at, response_sent_at
            ),
        }
        self.audit_service.record(
            "message_latency_observed",
            "success",
            conversation_id=conversation.id,
            message_id=message.id,
            payload=payload,
        )

    def _min_datetime(self, values) -> datetime | None:
        timestamps = [value for value in values if value is not None]
        return min(timestamps) if timestamps else None

    def _max_datetime(self, values) -> datetime | None:
        timestamps = [value for value in values if value is not None]
        return max(timestamps) if timestamps else None

    def _duration_ms(
        self, started_at: datetime | None, finished_at: datetime | None
    ) -> int | None:
        if not started_at or not finished_at:
            return None
        return max(0, int((finished_at - started_at).total_seconds() * 1000))

    def _isoformat(self, value: datetime | None) -> str | None:
        return value.isoformat() if value else None


def run_forever() -> None:
    configure_logging()
    settings = get_settings()
    shutdown = threading.Event()
    _install_shutdown_handlers(shutdown)

    with WorkerRuntime(settings) as runtime:
        if settings.queue_notify_active:
            _run_postgres_notify_forever(runtime, shutdown)
        else:
            _run_polling_forever(runtime, shutdown)


def _install_shutdown_handlers(shutdown: threading.Event) -> None:
    def request_shutdown(signum, frame) -> None:
        logger.info(
            "worker_shutdown_requested",
            extra={"payload": {"signal": signum}},
        )
        shutdown.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, request_shutdown)


def _process_once(runtime: WorkerRuntime) -> dict:
    with session_scope() as db:
        worker = runtime.create_worker(db)
        result = worker.process_once()
        logger.info("worker_tick", extra={"payload": result})
        return result


def _run_polling_forever(runtime: WorkerRuntime, shutdown: threading.Event) -> None:
    settings = runtime.settings
    backoff = PollingBackoff(
        settings.worker_sleep_seconds, settings.worker_backoff_max_seconds
    )
    while not shutdown.is_set():
        handled = _drain_queue(runtime)
        if handled == 0:
            sleep_seconds = backoff.next_empty_sleep()
            logger.info(
                "worker_queue_empty",
                extra={"payload": {"sleep_seconds": sleep_seconds}},
            )
            shutdown.wait(sleep_seconds)
            continue
        backoff.reset()


def _run_postgres_notify_forever(
    runtime: WorkerRuntime, shutdown: threading.Event
) -> None:
    settings = runtime.settings
    if not settings.database_url.startswith("postgres"):
        logger.warning(
            "worker_notify_unsupported_database",
            extra={"payload": {"fallback": "polling"}},
        )
        _run_polling_forever(runtime, shutdown)
        return

    listener = QueueListener(settings)
    try:
        _drain_queue(runtime)
        while not shutdown.is_set():
            notified = listener.wait(settings.effective_worker_fallback_poll_seconds)
            logger.info(
                "worker_wakeup",
                extra={
                    "payload": {
                        "wake_source": "postgres_notify"
                        if notified
                        else "fallback_poll"
                    }
                },
            )
            _drain_queue(runtime)
    finally:
        listener.close()


def _drain_queue(runtime: WorkerRuntime) -> int:
    handled = 0
    logger.info(
        "worker_drain_started",
        extra={"payload": {"max_batch": runtime.settings.worker_max_drain_batch}},
    )
    for _ in range(runtime.settings.worker_max_drain_batch):
        try:
            result = _process_once(runtime)
        except Exception as exc:
            logger.exception(
                "worker_drain_error",
                extra={"payload": {"error": str(exc)}},
            )
            break
        if result.get("reason") == "no_message":
            break
        handled += 1
    logger.info("worker_drain_finished", extra={"payload": {"handled": handled}})
    return handled


if __name__ == "__main__":
    run_forever()
