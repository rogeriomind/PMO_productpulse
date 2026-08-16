from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import AgentDispatchRecord, utcnow


class AgentDispatchRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_event_id(self, event_id: str) -> AgentDispatchRecord | None:
        return self.db.scalar(
            select(AgentDispatchRecord).where(AgentDispatchRecord.event_id == event_id)
        )

    def get(self, dispatch_id: str) -> AgentDispatchRecord | None:
        return self.db.get(AgentDispatchRecord, dispatch_id)

    def create(
        self,
        *,
        event_id: str,
        conversation_id: str,
        request_id: str,
        correlation_id: str,
        thread_id: str,
        source_message_ids: list[str],
        request_payload: dict,
    ) -> AgentDispatchRecord:
        record = AgentDispatchRecord(
            event_id=event_id,
            conversation_id=conversation_id,
            request_id=request_id,
            correlation_id=correlation_id,
            thread_id=thread_id,
            source_message_ids=source_message_ids,
            request_payload=request_payload,
            status="pending",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_calling(self, dispatch_id: str) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "calling_agent"
        record.attempts += 1
        record.agent_called_at = utcnow()
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def save_response(
        self, dispatch_id: str, response_payload: dict
    ) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.response_payload = response_payload
        record.status = "agent_completed"
        record.last_error = None
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_delivering(self, dispatch_id: str) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "delivering"
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_delivered(self, dispatch_id: str) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "delivered"
        record.delivered_at = utcnow()
        record.last_error = None
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_superseded(self, dispatch_id: str) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "superseded"
        record.superseded_at = utcnow()
        record.last_error = None
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_retry(
        self, dispatch_id: str, error_message: str
    ) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "retry"
        record.last_error = error_message
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_failed(
        self, dispatch_id: str, error_message: str
    ) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "failed"
        record.last_error = error_message
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def mark_delivery_failed(
        self, dispatch_id: str, error_message: str
    ) -> AgentDispatchRecord | None:
        record = self.get(dispatch_id)
        if not record:
            return None
        record.status = "agent_completed"
        record.last_error = error_message
        record.updated_at = utcnow()
        self.db.commit()
        self.db.refresh(record)
        return record

    def list_by_conversation(self, conversation_id: str) -> list[AgentDispatchRecord]:
        return list(
            self.db.scalars(
                select(AgentDispatchRecord)
                .where(AgentDispatchRecord.conversation_id == conversation_id)
                .order_by(AgentDispatchRecord.created_at)
            )
        )
