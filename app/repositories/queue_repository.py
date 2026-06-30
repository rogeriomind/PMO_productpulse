from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.database.connection import MessageRecord, QueueRecord, utcnow


class QueueRepository:
    OPEN_STATUSES = ("pending", "retry", "processing")

    def __init__(self, db: Session):
        self.db = db

    def enqueue(self, message_id: str, conversation_id: str) -> QueueRecord:
        record = QueueRecord(message_id=message_id, conversation_id=conversation_id)
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def lock_next(self, lock_seconds: int) -> QueueRecord | None:
        now = utcnow()
        stmt = (
            select(QueueRecord)
            .where(
                QueueRecord.status.in_(("pending", "retry")),
                or_(QueueRecord.locked_until.is_(None), QueueRecord.locked_until <= now),
            )
            .order_by(QueueRecord.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        record = self.db.scalar(stmt)
        if not record:
            return None
        record.status = "processing"
        record.attempts += 1
        record.locked_until = now + timedelta(seconds=lock_seconds)
        record.error_message = None
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_done(self, queue_id: str) -> None:
        record = self.db.get(QueueRecord, queue_id)
        if not record:
            return
        record.status = "done"
        record.locked_until = None
        record.error_message = None
        self.db.commit()

    def mark_done_many(self, queue_ids: list[str]) -> None:
        for queue_id in set(queue_ids):
            record = self.db.get(QueueRecord, queue_id)
            if record and record.status != "done":
                record.status = "done"
                record.locked_until = None
                record.error_message = None
        self.db.commit()

    def mark_retry(self, queue_id: str, error_message: str, max_attempts: int, delay_seconds: int = 0) -> str:
        record = self.db.get(QueueRecord, queue_id)
        if not record:
            return "missing"
        if record.attempts >= max_attempts:
            record.status = "failed"
            record.locked_until = None
            record.error_message = error_message
            result = "failed"
        else:
            record.status = "retry"
            record.locked_until = utcnow() + timedelta(seconds=delay_seconds)
            record.error_message = error_message
            result = "retry"
        self.db.commit()
        return result

    def postpone(self, queue_id: str, reason: str, delay_seconds: int) -> None:
        record = self.db.get(QueueRecord, queue_id)
        if not record:
            return
        record.status = "retry"
        record.locked_until = utcnow() + timedelta(seconds=delay_seconds)
        record.error_message = reason
        self.db.commit()

    def mark_failed(self, queue_id: str, error_message: str) -> None:
        record = self.db.get(QueueRecord, queue_id)
        if not record:
            return
        record.status = "failed"
        record.locked_until = None
        record.error_message = error_message
        self.db.commit()

    def list_open_text_items(self, conversation_id: str, exclude_queue_id: str | None = None) -> list[tuple[QueueRecord, MessageRecord]]:
        conditions = [
            QueueRecord.conversation_id == conversation_id,
            QueueRecord.status.in_(self.OPEN_STATUSES),
            MessageRecord.direction == "inbound",
            MessageRecord.message_type == "text",
        ]
        if exclude_queue_id:
            conditions.append(QueueRecord.id != exclude_queue_id)
        stmt = (
            select(QueueRecord, MessageRecord)
            .join(MessageRecord, MessageRecord.id == QueueRecord.message_id)
            .where(and_(*conditions))
            .order_by(MessageRecord.created_at)
        )
        return [(row[0], row[1]) for row in self.db.execute(stmt).all()]
