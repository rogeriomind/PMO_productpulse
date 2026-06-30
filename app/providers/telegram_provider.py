import httpx

from app.config import Settings, get_settings
from app.providers.message_provider import MessageProvider


class TelegramMessageProvider(MessageProvider):
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=10)

    def send_text(self, chat_id: str, text: str) -> dict:
        if not self.settings.telegram_bot_token:
            return {"ok": True, "mock": True, "chat_id": chat_id, "text": text}

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = self.client.post(url, json={"chat_id": chat_id, "text": text})
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("description") or data.get("message") or "Falha ao enviar mensagem Telegram"
            raise RuntimeError(message)
        return data
