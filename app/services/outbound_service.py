from app.database.connection import ConversationRecord
from app.models.channel_outbound_message import ChannelOutboundMessage
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

    def send(
        self, conversation: ConversationRecord, outbound: ChannelOutboundMessage
    ) -> dict:
        provider = self.providers.get(conversation.provider)
        if not provider:
            raise RuntimeError(
                f"Provider outbound não configurado: {conversation.provider}"
            )
        payload = {
            "provider": conversation.provider,
            "text": outbound.text,
            "metadata": outbound.metadata,
        }
        if outbound.reply_markup:
            payload["reply_markup"] = outbound.reply_markup
        try:
            result = provider.send_text(
                conversation.provider_chat_id,
                outbound.text,
                reply_markup=outbound.reply_markup,
            )
            self.message_repository.create_outbound(
                conversation_id=conversation.id,
                provider=conversation.provider,
                text=outbound.text,
                raw_payload={
                    "provider_result": result,
                    "reply_markup": outbound.reply_markup,
                    "metadata": outbound.metadata,
                },
            )
            self.audit_service.record(
                "outbound_sent",
                "success",
                conversation_id=conversation.id,
                payload={**payload, "result": result},
            )
            return result
        except Exception as exc:
            self.audit_service.record(
                "outbound_failed",
                "failed",
                conversation_id=conversation.id,
                payload=payload,
                error_message=str(exc),
            )
            raise

    def send_text(
        self,
        conversation: ConversationRecord,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        return self.send(
            conversation, ChannelOutboundMessage(text=text, reply_markup=reply_markup)
        )
