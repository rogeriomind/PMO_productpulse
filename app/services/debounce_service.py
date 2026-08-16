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
    message_ids: list[str]
    remaining_seconds: float = 0


class DebounceService:
    def __init__(
        self,
        debounce_repository: DebounceRepository,
        message_repository: MessageRepository,
        queue_repository: QueueRepository,
        audit_service: AuditService,
        debounce_seconds: float,
        debounce_max_seconds: float,
        *,
        adaptive_enabled: bool = False,
        debounce_min_seconds: float | None = None,
        debounce_increment_seconds: float = 0.4,
        debounce_max_messages: int = 8,
        adaptive_max_seconds: float | None = None,
    ):
        self.debounce_repository = debounce_repository
        self.message_repository = message_repository
        self.queue_repository = queue_repository
        self.audit_service = audit_service
        self.debounce_seconds = debounce_seconds
        self.debounce_max_seconds = debounce_max_seconds
        self.adaptive_enabled = adaptive_enabled
        self.debounce_min_seconds = (
            debounce_min_seconds
            if debounce_min_seconds is not None
            else debounce_seconds
        )
        self.debounce_increment_seconds = debounce_increment_seconds
        self.debounce_max_messages = debounce_max_messages
        self.adaptive_max_seconds = adaptive_max_seconds or debounce_max_seconds

    def assess_text(
        self, conversation_id: str, message_id: str | None = None
    ) -> DebounceDecision:
        items = self.queue_repository.list_open_text_items(conversation_id)
        if not items:
            return DebounceDecision(False, "", [], [])

        combined_text = " ".join(
            (message.normalized_text or "").strip() for _, message in items
        ).strip()
        queue_ids = [queue.id for queue, _ in items]
        message_ids = [message.id for _, message in items]
        message_times = [message.created_at for _, message in items]
        first_message_at = min(message_times)
        last_message_at = max(message_times)
        now = utcnow()
        elapsed_since_first = (now - first_message_at).total_seconds()
        elapsed_since_last = (now - last_message_at).total_seconds()
        fragment_count = len(items)
        debounce_window = self._debounce_window_seconds(fragment_count)
        max_window = self._max_window_seconds()
        should_wait = (
            fragment_count < self.debounce_max_messages
            and elapsed_since_last < debounce_window
            and elapsed_since_first < max_window
        )

        if should_wait:
            debounce_remaining = debounce_window - elapsed_since_last
            max_remaining = max_window - elapsed_since_first
            remaining = max(0.0, min(debounce_remaining, max_remaining))
            self.debounce_repository.upsert_open(conversation_id, combined_text)
            self.queue_repository.mark_debounce_started_many(queue_ids)
            self.audit_service.record(
                "debounce_extended" if fragment_count > 1 else "debounce_started",
                "waiting",
                conversation_id=conversation_id,
                message_id=message_id,
                payload={
                    "debounce_started_at": first_message_at.isoformat(),
                    "message_received_at": last_message_at.isoformat(),
                    "debounce_ms": int(debounce_window * 1000),
                    "fragments": fragment_count,
                    "remaining_seconds": remaining,
                    "queue_ids": queue_ids,
                },
            )
            return DebounceDecision(
                True, combined_text, queue_ids, message_ids, remaining
            )

        self.debounce_repository.flush_open(conversation_id, combined_text)
        self.queue_repository.mark_debounce_finished_many(queue_ids)
        self.audit_service.record(
            "debounce_flushed",
            "success",
            conversation_id=conversation_id,
            message_id=message_id,
            payload={
                "debounce_started_at": first_message_at.isoformat(),
                "debounce_finished_at": now.isoformat(),
                "debounce_wait_ms": int(elapsed_since_first * 1000),
                "debounce_ms": int(debounce_window * 1000),
                "fragments": fragment_count,
                "queue_ids": queue_ids,
                "combined_text": combined_text,
            },
        )
        return DebounceDecision(False, combined_text, queue_ids, message_ids)

    def _debounce_window_seconds(self, fragment_count: int) -> float:
        if not self.adaptive_enabled:
            return self.debounce_seconds
        increments = max(0, fragment_count - 1) * self.debounce_increment_seconds
        return min(self.debounce_min_seconds + increments, self._max_window_seconds())

    def _max_window_seconds(self) -> float:
        return (
            self.adaptive_max_seconds
            if self.adaptive_enabled
            else self.debounce_max_seconds
        )

    def flush_pending_texts(
        self, conversation_id: str, exclude_queue_id: str | None = None
    ) -> DebounceDecision | None:
        items = self.queue_repository.list_open_text_items(
            conversation_id, exclude_queue_id=exclude_queue_id
        )
        if not items:
            return None
        combined_text = " ".join(
            (message.normalized_text or "").strip() for _, message in items
        ).strip()
        queue_ids = [queue.id for queue, _ in items]
        message_ids = [message.id for _, message in items]
        self.debounce_repository.flush_open(conversation_id, combined_text)
        self.queue_repository.mark_debounce_finished_many(queue_ids)
        self.audit_service.record(
            "debounce_flushed",
            "success",
            conversation_id=conversation_id,
            payload={
                "forced_by_audio": True,
                "queue_ids": queue_ids,
                "combined_text": combined_text,
            },
        )
        return DebounceDecision(False, combined_text, queue_ids, message_ids)
