from app.database.connection import ConversationRecord
from app.providers.message_provider import MessageProvider
from app.repositories.message_repository import MessageRepository
from app.services.audit_service import AuditService


class OutboundService:
    def __init__(
        self,
        message_repository: MessageRepository,
        audit_service: AuditService,
        providers: dict[str, MessageProvider],
    ):
        self.message_repository = message_repository
        self.audit_service = audit_service
        self.providers = providers

    def send_text(self, conversation: ConversationRecord, text: str) -> dict:
        provider = self.providers.get(conversation.provider)
        if not provider:
            raise RuntimeError(f"Provider outbound não configurado: {conversation.provider}")
        try:
            result = provider.send_text(conversation.provider_chat_id, text)
            self.message_repository.create_outbound(
                conversation_id=conversation.id,
                provider=conversation.provider,
                text=text,
                raw_payload=result,
            )
            self.audit_service.record(
                "outbound_sent",
                "success",
                conversation_id=conversation.id,
                payload={"provider": conversation.provider, "text": text, "result": result},
            )
            return result
        except Exception as exc:
            self.audit_service.record(
                "outbound_failed",
                "failed",
                conversation_id=conversation.id,
                payload={"provider": conversation.provider, "text": text},
                error_message=str(exc),
            )
            raise
