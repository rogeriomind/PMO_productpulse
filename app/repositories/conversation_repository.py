from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.connection import ConversationRecord


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, provider: str, provider_chat_id: str, provider_user_id: str | None = None) -> ConversationRecord:
        conversation = self.db.scalar(
            select(ConversationRecord).where(
                ConversationRecord.provider == provider,
                ConversationRecord.provider_chat_id == provider_chat_id,
            )
        )
        if conversation:
            if provider_user_id and conversation.provider_user_id != provider_user_id:
                conversation.provider_user_id = provider_user_id
                self.db.commit()
                self.db.refresh(conversation)
            return conversation

        conversation = ConversationRecord(
            provider=provider,
            provider_chat_id=provider_chat_id,
            provider_user_id=provider_user_id,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get(self, conversation_id: str) -> ConversationRecord | None:
        return self.db.get(ConversationRecord, conversation_id)
