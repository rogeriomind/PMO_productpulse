from sqlalchemy.orm import Session

from app.config import Settings
from app.providers.telegram_provider import TelegramMessageProvider
from app.providers.whatsapp_provider_mock import WhatsAppMessageProviderMock
from app.repositories.audit_repository import AuditRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.services.audit_service import AuditService
from app.services.inbound_normalizer import InboundNormalizer
from app.services.outbound_service import OutboundService
from app.services.queue_service import QueueService
from app.services.rate_limit_service import RateLimitService


RATE_LIMIT_TEXT = "Recebi muitas mensagens em sequência. Aguarde alguns segundos e tente novamente."


class InboundService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings
        self.audit_service = AuditService(AuditRepository(db))
        self.conversation_repository = ConversationRepository(db)
        self.message_repository = MessageRepository(db)
        self.queue_service = QueueService(
            QueueRepository(db),
            lock_seconds=settings.queue_lock_seconds,
            max_attempts=settings.max_queue_attempts,
        )
        self.normalizer = InboundNormalizer()
        self.outbound_service = OutboundService(
            self.message_repository,
            self.audit_service,
            {
                "telegram": TelegramMessageProvider(settings),
                "whatsapp": WhatsAppMessageProviderMock(),
            },
        )

    def receive(self, provider: str, payload: dict) -> dict:
        self.audit_service.record("webhook_received", "success", payload={"provider": provider})
        try:
            normalized = self.normalizer.normalize(provider, payload)
            self.audit_service.record("payload_validated", "success", payload={"provider": provider})
            self.audit_service.record("message_normalized", "success", payload=normalized.model_dump(exclude={"raw_payload"}))
        except ValueError as exc:
            self.audit_service.record("payload_invalid", "failed", payload={"provider": provider}, error_message=str(exc))
            return {"status": "invalid", "error": str(exc)}

        conversation = self.conversation_repository.get_or_create(
            normalized.provider,
            normalized.provider_chat_id,
            normalized.provider_user_id,
        )

        rate_limit = RateLimitService(
            self.message_repository,
            self.audit_service,
            self.settings.rate_limit_max_messages,
            self.settings.rate_limit_window_seconds,
        )
        if not rate_limit.is_allowed(conversation.id):
            self.outbound_service.send_text(conversation, RATE_LIMIT_TEXT)
            return {"status": "rate_limited", "conversation_id": conversation.id}

        if self.message_repository.exists_provider_message(normalized.provider, normalized.provider_message_id):
            return {"status": "duplicate", "conversation_id": conversation.id}

        message = self.message_repository.create_inbound(conversation.id, normalized)
        self.audit_service.record(
            "message_persisted",
            "success",
            conversation_id=conversation.id,
            message_id=message.id,
            payload={"message_type": message.message_type},
        )
        queue_item = self.queue_service.enqueue(message.id, conversation.id)
        self.audit_service.record(
            "message_queued",
            "success",
            conversation_id=conversation.id,
            message_id=message.id,
            payload={"queue_id": queue_item.id},
        )
        return {"status": "queued", "conversation_id": conversation.id, "message_id": message.id, "queue_id": queue_item.id}
