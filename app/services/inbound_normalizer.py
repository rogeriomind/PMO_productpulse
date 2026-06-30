from typing import Any

from pydantic import ValidationError

from app.models.normalized_message import NormalizedMessage


class InboundNormalizer:
    def normalize(self, provider: str, payload: dict[str, Any]) -> NormalizedMessage:
        if provider == "telegram":
            return self._normalize_telegram(payload)
        if provider == "whatsapp":
            return self._normalize_whatsapp(payload)
        raise ValueError(f"Provider não suportado: {provider}")

    def _normalize_telegram(self, payload: dict[str, Any]) -> NormalizedMessage:
        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            raise ValueError("Payload Telegram não contém message")

        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            raise ValueError("Payload Telegram sem chat.id")

        message_type = "unknown"
        text = None
        media_file_id = None
        media_url = None

        if message.get("text"):
            message_type = "text"
            text = str(message["text"]).strip()
        elif message.get("voice") or message.get("audio"):
            media = message.get("voice") or message.get("audio")
            message_type = "audio"
            media_file_id = str(media.get("file_id")) if media.get("file_id") else None
        elif message.get("photo"):
            message_type = "image"
            photos = message.get("photo") or []
            if photos:
                media_file_id = str(photos[-1].get("file_id"))

        try:
            return NormalizedMessage(
                provider="telegram",
                provider_chat_id=str(chat_id),
                provider_user_id=str(sender.get("id")) if sender.get("id") is not None else None,
                provider_message_id=str(message.get("message_id")) if message.get("message_id") is not None else None,
                message_type=message_type,
                text=text,
                media_file_id=media_file_id,
                media_url=media_url,
                raw_payload=payload,
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def _normalize_whatsapp(self, payload: dict[str, Any]) -> NormalizedMessage:
        if "provider_chat_id" in payload:
            return NormalizedMessage(
                provider="whatsapp",
                provider_chat_id=str(payload["provider_chat_id"]),
                provider_user_id=str(payload.get("provider_user_id")) if payload.get("provider_user_id") else None,
                provider_message_id=str(payload.get("provider_message_id")) if payload.get("provider_message_id") else None,
                message_type=payload.get("message_type", "text"),
                text=payload.get("text"),
                media_file_id=payload.get("media_file_id"),
                media_url=payload.get("media_url"),
                raw_payload=payload,
            )

        try:
            value = payload["entry"][0]["changes"][0]["value"]
            message = value["messages"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError("Payload WhatsApp mock inválido") from exc

        message_type = message.get("type", "unknown")
        text = None
        media_file_id = None
        if message_type == "text":
            text = message.get("text", {}).get("body")
        elif message_type == "audio":
            media_file_id = message.get("audio", {}).get("id")
        else:
            message_type = "unknown"

        return NormalizedMessage(
            provider="whatsapp",
            provider_chat_id=str(message.get("from")),
            provider_user_id=str(message.get("from")),
            provider_message_id=str(message.get("id")) if message.get("id") else None,
            message_type=message_type,
            text=text,
            media_file_id=media_file_id,
            raw_payload=payload,
        )
