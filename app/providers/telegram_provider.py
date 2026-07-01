import httpx

from app.config import Settings, get_settings
from app.providers.message_provider import MessageProvider


class TelegramMessageProvider(MessageProvider):
    def __init__(self, settings: Settings | None = None, client: httpx.Client | None = None):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=10)

    def send_text(self, chat_id: str, text: str, reply_markup: dict | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text}
        if reply_markup:
            payload["reply_markup"] = reply_markup

        if not self.settings.telegram_bot_token:
            return {"ok": True, "mock": True, **payload}

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = self.client.post(url, json=payload)
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("description") or data.get("message") or "Falha ao enviar mensagem Telegram"
            raise RuntimeError(message)
        return data

    def answer_callback(self, callback_query_id: str, text: str | None = None) -> dict:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text

        if not self.settings.telegram_bot_token:
            return {"ok": True, "mock": True, **payload}

        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/answerCallbackQuery"
        response = self.client.post(url, json=payload)
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("description") or data.get("message") or "Falha ao confirmar callback Telegram"
            raise RuntimeError(message)
        return data
