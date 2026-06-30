import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import TaskActionRecord, utcnow


class TaskActionRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_pending(
        self,
        conversation_id: str,
        user_id: str | None,
        intent: str,
        action_payload: dict,
    ) -> TaskActionRecord:
        record = TaskActionRecord(
            conversation_id=conversation_id,
            user_id=user_id,
            intent=intent,
            action_payload=action_payload,
            status="pending_confirmation",
            confirmation_token=secrets.token_urlsafe(12),
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get(self, action_id: str) -> TaskActionRecord | None:
        return self.db.get(TaskActionRecord, action_id)

    def latest_pending(self, conversation_id: str) -> TaskActionRecord | None:
        return self.db.scalar(
            select(TaskActionRecord)
            .where(
                TaskActionRecord.conversation_id == conversation_id,
                TaskActionRecord.status == "pending_confirmation",
            )
            .order_by(TaskActionRecord.created_at.desc())
            .limit(1)
        )

    def list_by_conversation(self, conversation_id: str) -> list[TaskActionRecord]:
        return list(
            self.db.scalars(
                select(TaskActionRecord)
                .where(TaskActionRecord.conversation_id == conversation_id)
                .order_by(TaskActionRecord.created_at)
            )
        )

    def mark_confirmed(self, action_id: str) -> TaskActionRecord | None:
        record = self.get(action_id)
        if not record:
            return None
        record.status = "confirmed"
        record.confirmed_at = utcnow()
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_canceled(self, action_id: str) -> TaskActionRecord | None:
        record = self.get(action_id)
        if not record:
            return None
        record.status = "canceled"
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_executed(self, action_id: str, result_payload: dict) -> TaskActionRecord | None:
        record = self.get(action_id)
        if not record:
            return None
        record.status = "executed"
        record.executed_at = utcnow()
        record.result_payload = result_payload
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_failed(self, action_id: str, error_message: str) -> TaskActionRecord | None:
        record = self.get(action_id)
        if not record:
            return None
        record.status = "failed"
        record.error_message = error_message
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record
