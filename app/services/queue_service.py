from app.repositories.queue_repository import QueueRepository
from app.services.queue_notification_service import QueueNotificationService


class QueueService:
    def __init__(
        self,
        repository: QueueRepository,
        lock_seconds: int,
        max_attempts: int,
        notification_service: QueueNotificationService | None = None,
    ):
        self.repository = repository
        self.lock_seconds = lock_seconds
        self.max_attempts = max_attempts
        self.notification_service = notification_service

    def enqueue(self, message_id: str, conversation_id: str):
        record = self.repository.enqueue(message_id, conversation_id)
        if self.notification_service:
            self.notification_service.notify_new_item(record.id)
        return record

    def lock_next(self):
        return self.repository.lock_next(self.lock_seconds)

    def mark_done(self, queue_id: str) -> None:
        self.repository.mark_done(queue_id)

    def mark_done_many(self, queue_ids: list[str]) -> None:
        self.repository.mark_done_many(queue_ids)

    def retry_or_fail(
        self, queue_id: str, error_message: str, delay_seconds: float = 0
    ) -> str:
        return self.repository.mark_retry(
            queue_id, error_message, self.max_attempts, delay_seconds
        )

    def postpone(self, queue_id: str, reason: str, delay_seconds: float) -> None:
        self.repository.postpone(queue_id, reason, delay_seconds)

    def mark_failed(self, queue_id: str, error_message: str) -> None:
        self.repository.mark_failed(queue_id, error_message)

    def mark_debounce_started_many(self, queue_ids: list[str]) -> None:
        self.repository.mark_debounce_started_many(queue_ids)

    def mark_debounce_finished_many(self, queue_ids: list[str]) -> None:
        self.repository.mark_debounce_finished_many(queue_ids)

    def mark_ia_request_started_many(self, queue_ids: list[str]) -> None:
        self.repository.mark_ia_request_started_many(queue_ids)

    def mark_ia_response_received_many(self, queue_ids: list[str]) -> None:
        self.repository.mark_ia_response_received_many(queue_ids)

    def mark_response_sent_many(self, queue_ids: list[str]) -> None:
        self.repository.mark_response_sent_many(queue_ids)
