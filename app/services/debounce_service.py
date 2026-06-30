from dataclasses import dataclass

from app.database.connection import utcnow
from app.repositories.debounce_repository import DebounceRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.services.audit_service import AuditService


@dataclass
class DebounceDecision:
    should_wait: bool
    combined_text: str
    queue_ids: list[str]
    remaining_seconds: int = 0


class DebounceService:
    def __init__(
        self,
        debounce_repository: DebounceRepository,
        message_repository: MessageRepository,
        queue_repository: QueueRepository,
        audit_service: AuditService,
        debounce_seconds: int,
    ):
        self.debounce_repository = debounce_repository
        self.message_repository = message_repository
        self.queue_repository = queue_repository
        self.audit_service = audit_service
        self.debounce_seconds = debounce_seconds

    def assess_text(self, conversation_id: str, message_id: str | None = None) -> DebounceDecision:
        items = self.queue_repository.list_open_text_items(conversation_id)
        combined_text = " ".join((message.normalized_text or "").strip() for _, message in items).strip()
        queue_ids = [queue.id for queue, _ in items]
        last_message_at = self.message_repository.last_inbound_at(conversation_id, "text")
        elapsed = (utcnow() - last_message_at).total_seconds() if last_message_at else self.debounce_seconds

        if elapsed < self.debounce_seconds:
            remaining = max(1, int(self.debounce_seconds - elapsed))
            self.debounce_repository.upsert_open(conversation_id, combined_text)
            self.audit_service.record(
                "debounce_waiting",
                "waiting",
                conversation_id=conversation_id,
                message_id=message_id,
                payload={"remaining_seconds": remaining, "queue_ids": queue_ids},
            )
            return DebounceDecision(True, combined_text, queue_ids, remaining)

        self.debounce_repository.flush_open(conversation_id, combined_text)
        self.audit_service.record(
            "debounce_flushed",
            "success",
            conversation_id=conversation_id,
            message_id=message_id,
            payload={"queue_ids": queue_ids, "combined_text": combined_text},
        )
        return DebounceDecision(False, combined_text, queue_ids)

    def flush_pending_texts(self, conversation_id: str, exclude_queue_id: str | None = None) -> DebounceDecision | None:
        items = self.queue_repository.list_open_text_items(conversation_id, exclude_queue_id=exclude_queue_id)
        if not items:
            return None
        combined_text = " ".join((message.normalized_text or "").strip() for _, message in items).strip()
        queue_ids = [queue.id for queue, _ in items]
        self.debounce_repository.flush_open(conversation_id, combined_text)
        self.audit_service.record(
            "debounce_flushed",
            "success",
            conversation_id=conversation_id,
            payload={"forced_by_audio": True, "queue_ids": queue_ids, "combined_text": combined_text},
        )
        return DebounceDecision(False, combined_text, queue_ids)
