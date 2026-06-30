from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import AuditLogRecord


class AuditRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        event_type: str,
        status: str,
        conversation_id: str | None = None,
        message_id: str | None = None,
        payload: dict | None = None,
        error_message: str | None = None,
    ) -> AuditLogRecord:
        record = AuditLogRecord(
            conversation_id=conversation_id,
            message_id=message_id,
            event_type=event_type,
            status=status,
            payload=payload or {},
            error_message=error_message,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_by_conversation(self, conversation_id: str) -> list[AuditLogRecord]:
        return list(
            self.db.scalars(
                select(AuditLogRecord)
                .where(AuditLogRecord.conversation_id == conversation_id)
                .order_by(AuditLogRecord.created_at)
            )
        )
