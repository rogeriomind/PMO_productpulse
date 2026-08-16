from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import DebounceBufferRecord, utcnow


class DebounceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_open(self, conversation_id: str) -> DebounceBufferRecord | None:
        return self.db.scalar(
            select(DebounceBufferRecord)
            .where(
                DebounceBufferRecord.conversation_id == conversation_id,
                DebounceBufferRecord.status == "open",
            )
            .order_by(DebounceBufferRecord.created_at.desc())
            .limit(1)
        )

    def upsert_open(
        self, conversation_id: str, combined_text: str
    ) -> DebounceBufferRecord:
        record = self.get_open(conversation_id)
        if not record:
            record = DebounceBufferRecord(conversation_id=conversation_id)
            self.db.add(record)
        record.combined_text = combined_text
        record.last_message_at = utcnow()
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def flush_open(
        self, conversation_id: str, combined_text: str | None = None
    ) -> DebounceBufferRecord | None:
        record = self.get_open(conversation_id)
        if not record:
            return None
        if combined_text is not None:
            record.combined_text = combined_text
        record.status = "flushed"
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record
