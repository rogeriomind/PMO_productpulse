import unicodedata

from app.database.connection import TaskActionRecord
from app.repositories.task_action_repository import TaskActionRepository
from app.services.audit_service import AuditService


class ConfirmationService:
    CONFIRM_WORDS = ("confirmo", "confirma", "sim", "pode fazer", "ok", "manda")
    CANCEL_WORDS = ("cancela", "nao", "não", "deixa", "ignora")

    def __init__(self, repository: TaskActionRepository, audit_service: AuditService):
        self.repository = repository
        self.audit_service = audit_service

    def is_confirmation(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(word in normalized for word in self.CONFIRM_WORDS)

    def is_cancellation(self, text: str) -> bool:
        normalized = self._normalize(text)
        return any(self._normalize(word) in normalized for word in self.CANCEL_WORDS)

    def create_pending_action(
        self,
        conversation_id: str,
        user_id: str | None,
        intent: str,
        action_payload: dict,
    ) -> TaskActionRecord:
        action = self.repository.create_pending(conversation_id, user_id, intent, action_payload)
        self.audit_service.record(
            "confirmation_created",
            "success",
            conversation_id=conversation_id,
            payload={"action_id": action.id, "intent": intent, "type": action_payload.get("type")},
        )
        return action

    def confirm_latest(self, conversation_id: str) -> TaskActionRecord | None:
        action = self.repository.latest_pending(conversation_id)
        if not action:
            return None
        confirmed = self.repository.mark_confirmed(action.id)
        self.audit_service.record(
            "confirmation_confirmed",
            "success",
            conversation_id=conversation_id,
            payload={"action_id": action.id},
        )
        return confirmed

    def cancel_latest(self, conversation_id: str) -> TaskActionRecord | None:
        action = self.repository.latest_pending(conversation_id)
        if not action:
            return None
        canceled = self.repository.mark_canceled(action.id)
        self.audit_service.record(
            "confirmation_canceled",
            "success",
            conversation_id=conversation_id,
            payload={"action_id": action.id},
        )
        return canceled

    def _normalize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.lower().strip())
        return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
