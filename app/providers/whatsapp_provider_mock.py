from app.providers.message_provider import MessageProvider


class WhatsAppMessageProviderMock(MessageProvider):
    def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
        return {"ok": True, "mock": True, "provider": "whatsapp", "chat_id": chat_id, "text": text}
