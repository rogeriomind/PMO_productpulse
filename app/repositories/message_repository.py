from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.connection import MessageRecord
from app.models.normalized_message import NormalizedMessage


class MessageRepository:
    def __init__(self, db: Session):
        self.db = db

    def exists_provider_message(
        self, provider: str, provider_message_id: str | None
    ) -> bool:
        if not provider_message_id:
            return False
        exists = self.db.scalar(
            select(MessageRecord.id).where(
                MessageRecord.provider == provider,
                MessageRecord.provider_message_id == provider_message_id,
            )
        )
        return exists is not None

    def exists_event(self, event_id: str | None) -> bool:
        if not event_id:
            return False
        exists = self.db.scalar(
            select(MessageRecord.id).where(MessageRecord.event_id == event_id)
        )
        return exists is not None

    def create_inbound(
        self, conversation_id: str, message: NormalizedMessage
    ) -> MessageRecord:
        record = MessageRecord(
            conversation_id=conversation_id,
            provider=message.provider,
            provider_message_id=message.provider_message_id,
            provider_update_id=message.provider_update_id,
            event_id=message.event_id,
            direction="inbound",
            message_type=message.content_type,
            content_type=message.content_type,
            raw_payload=message.raw_payload,
            normalized_text=message.text,
            callback_query_id=message.callback_query_id,
            callback_data=message.callback_data,
            media_file_id=message.media_file_id,
            media_url=message.media_url,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def create_outbound(
        self,
        conversation_id: str,
        provider: str,
        text: str,
        raw_payload: dict | None = None,
    ) -> MessageRecord:
        record = MessageRecord(
            conversation_id=conversation_id,
            provider=provider,
            provider_message_id=None,
            provider_update_id=None,
            event_id=None,
            direction="outbound",
            message_type="text",
            content_type="text",
            raw_payload=raw_payload or {},
            normalized_text=text,
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get(self, message_id: str) -> MessageRecord | None:
        return self.db.get(MessageRecord, message_id)

    def list_by_conversation(self, conversation_id: str) -> list[MessageRecord]:
        return list(
            self.db.scalars(
                select(MessageRecord)
                .where(MessageRecord.conversation_id == conversation_id)
                .order_by(MessageRecord.created_at)
            )
        )

    def count_recent_inbound(self, conversation_id: str, since: datetime) -> int:
        return int(
            self.db.scalar(
                select(func.count(MessageRecord.id)).where(
                    MessageRecord.conversation_id == conversation_id,
                    MessageRecord.direction == "inbound",
                    MessageRecord.created_at >= since,
                )
            )
            or 0
        )

    def last_inbound_at(
        self, conversation_id: str, message_type: str | None = None
    ) -> datetime | None:
        conditions = [
            MessageRecord.conversation_id == conversation_id,
            MessageRecord.direction == "inbound",
        ]
        if message_type:
            conditions.append(MessageRecord.message_type == message_type)
        return self.db.scalar(
            select(func.max(MessageRecord.created_at)).where(*conditions)
        )

    def has_newer_inbound(
        self, conversation_id: str, source_message_ids: list[str]
    ) -> bool:
        source_ids = [message_id for message_id in source_message_ids if message_id]
        if not source_ids:
            return False

        cutoff = self.db.scalar(
            select(func.max(MessageRecord.created_at)).where(
                MessageRecord.conversation_id == conversation_id,
                MessageRecord.id.in_(source_ids),
            )
        )
        if not cutoff:
            return False

        exists = self.db.scalar(
            select(MessageRecord.id)
            .where(
                MessageRecord.conversation_id == conversation_id,
                MessageRecord.direction == "inbound",
                MessageRecord.created_at > cutoff,
                MessageRecord.id.notin_(source_ids),
            )
            .limit(1)
        )
        return exists is not None
