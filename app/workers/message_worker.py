import logging
import time

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.connection import session_scope
from app.logging_config import configure_logging
from app.providers.mock_transcription_provider import MockTranscriptionProvider
from app.providers.pmo_board_auth_provider import PmoBoardAuthProvider
from app.providers.pmo_board_provider import PmoBoardProvider
from app.providers.telegram_provider import TelegramMessageProvider
from app.providers.whatsapp_provider_mock import WhatsAppMessageProviderMock
from app.repositories.audit_repository import AuditRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.debounce_repository import DebounceRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.repositories.task_action_repository import TaskActionRepository
from app.services.audit_service import AuditService
from app.services.board_context_service import BoardContextService
from app.services.board_service import BoardService
from app.services.confirmation_service import ConfirmationService
from app.services.debounce_service import DebounceService
from app.services.mock_agent_service import MockAgentService
from app.services.outbound_service import OutboundService
from app.services.preprocessing_service import PreprocessingService
from app.services.queue_service import QueueService

logger = logging.getLogger(__name__)


class MessageWorker:
    def __init__(self, db: Session, settings: Settings | None = None):
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
        self.confirmation_service = ConfirmationService(TaskActionRepository(db), self.audit_service)
        self.preprocessing_service = PreprocessingService(MockTranscriptionProvider(), self.audit_service)
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
        auth_provider = PmoBoardAuthProvider(self.settings, audit_service=self.audit_service)
        board_provider = PmoBoardProvider(self.settings, auth_provider=auth_provider)
        self.board_context_service = BoardContextService(board_provider, self.audit_service)
        self.board_service = BoardService(
            board_provider,
            self.board_context_service,
            self.confirmation_service,
            self.audit_service,
        )
        self.agent_service = MockAgentService()

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
            self.queue_service.mark_failed(queue_item.id, "Mensagem ou conversa não encontrada")
            return {"processed": False, "reason": "missing_records"}

        try:
            response_text = self._handle_message(conversation, message, queue_item.id)
            if response_text is None:
                return {"processed": False, "reason": "deferred", "queue_id": queue_item.id}
            if response_text:
                self.outbound_service.send_text(conversation, response_text)
            self.audit_service.record(
                "queue_done",
                "success",
                conversation_id=conversation.id,
                message_id=message.id,
                payload={"queue_id": queue_item.id},
            )
            return {"processed": True, "queue_id": queue_item.id}
        except Exception as exc:
            result = self.queue_service.retry_or_fail(queue_item.id, str(exc))
            event = "queue_failed" if result == "failed" else "queue_retry"
            self.audit_service.record(
                event,
                result,
                conversation_id=conversation.id,
                message_id=message.id,
                payload={"queue_id": queue_item.id},
                error_message=str(exc),
            )
            return {"processed": False, "reason": result, "error": str(exc)}

    def _handle_message(self, conversation, message, queue_id: str) -> str | None:
        if message.message_type in ("image", "unknown"):
            self.queue_service.mark_done(queue_id)
            return "Recebi a mensagem, mas neste MVP só consigo tratar texto e áudio."

        control_text = (message.normalized_text or "").strip()
        if control_text and self.confirmation_service.is_cancellation(control_text):
            action = self.confirmation_service.cancel_latest(conversation.id)
            self.queue_service.mark_done(queue_id)
            if not action:
                return "Não encontrei ação pendente para cancelar."
            return "Ação cancelada. Nenhuma alteração foi feita no board."

        if control_text and self.confirmation_service.is_confirmation(control_text):
            action = self.confirmation_service.confirm_latest(conversation.id)
            self.queue_service.mark_done(queue_id)
            if not action:
                return "Não encontrei ação pendente para confirmar."
            return self.board_service.execute_confirmed_action(action)

        if message.message_type == "text":
            decision = self.debounce_service.assess_text(conversation.id, message.id)
            if decision.should_wait:
                self.queue_service.postpone(queue_id, "debounce_waiting", decision.remaining_seconds)
                self.audit_service.record(
                    "queue_retry",
                    "debounce_waiting",
                    conversation_id=conversation.id,
                    message_id=message.id,
                    payload={"queue_id": queue_id, "delay_seconds": decision.remaining_seconds},
                )
                return None
            input_text = self.preprocessing_service.process(message, override_text=decision.combined_text)
            response = self._process_agent_input(conversation.id, conversation.provider_user_id, input_text)
            self.queue_service.mark_done_many(decision.queue_ids or [queue_id])
            return response

        if message.message_type == "audio":
            flushed = self.debounce_service.flush_pending_texts(conversation.id, exclude_queue_id=queue_id)
            if flushed and flushed.combined_text:
                text_response = self._process_agent_input(conversation.id, conversation.provider_user_id, flushed.combined_text)
                if text_response:
                    self.outbound_service.send_text(conversation, text_response)
                self.queue_service.mark_done_many(flushed.queue_ids)
            input_text = self.preprocessing_service.process(message)
            response = self._process_agent_input(conversation.id, conversation.provider_user_id, input_text)
            self.queue_service.mark_done(queue_id)
            return response

        self.queue_service.mark_done(queue_id)
        return "Recebi a mensagem, mas este tipo ainda não está habilitado no MVP."

    def _process_agent_input(self, conversation_id: str, user_id: str | None, input_text: str) -> str:
        self.audit_service.record(
            "mock_agent_called",
            "started",
            conversation_id=conversation_id,
            payload={"input_text": input_text},
        )
        try:
            result = self.agent_service.process(conversation_id, user_id, input_text, context={})
            self.audit_service.record(
                "mock_agent_success",
                "success",
                conversation_id=conversation_id,
                payload=result.model_dump(),
            )
            return self.board_service.handle_agent_result(conversation_id, user_id, input_text, result)
        except Exception as exc:
            self.audit_service.record(
                "mock_agent_failed",
                "failed",
                conversation_id=conversation_id,
                payload={"input_text": input_text},
                error_message=str(exc),
            )
            raise


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
