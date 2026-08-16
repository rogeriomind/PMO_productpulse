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
        callback = payload.get("callback_query")
        if isinstance(callback, dict):
            return self._normalize_telegram_callback(payload, callback)

        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            raise ValueError("Payload Telegram não contém message")

        chat = message.get("chat") or {}
        sender = message.get("from") or {}
        chat_id = chat.get("id")
        update_id = payload.get("update_id")
        if chat_id is None:
            raise ValueError("Payload Telegram sem chat.id")
        if update_id is None:
            raise ValueError("Payload Telegram sem update_id")

        content_type = "unknown"
        text = None
        media_file_id = None
        media_url = None

        if message.get("text"):
            content_type = "text"
            text = str(message["text"]).strip()
        elif message.get("voice") or message.get("audio"):
            media = message.get("voice") or message.get("audio")
            content_type = "audio"
            media_file_id = str(media.get("file_id")) if media.get("file_id") else None
        elif message.get("photo"):
            content_type = "image"
            photos = message.get("photo") or []
            if photos:
                media_file_id = str(photos[-1].get("file_id"))

        try:
            return NormalizedMessage(
                provider="telegram",
                provider_chat_id=str(chat_id),
                provider_user_id=str(sender.get("id"))
                if sender.get("id") is not None
                else None,
                provider_user_name=self._telegram_user_name(sender),
                provider_username=str(sender.get("username"))
                if sender.get("username")
                else None,
                provider_message_id=str(message.get("message_id"))
                if message.get("message_id") is not None
                else None,
                provider_update_id=str(update_id),
                event_id=f"telegram:update:{update_id}",
                content_type=content_type,
                text=text,
                media_file_id=media_file_id,
                media_url=media_url,
                raw_payload=payload,
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def _normalize_telegram_callback(
        self, payload: dict[str, Any], callback: dict[str, Any]
    ) -> NormalizedMessage:
        sender = callback.get("from") or {}
        callback_message = callback.get("message") or {}
        chat = callback_message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            chat_id = sender.get("id")
        if chat_id is None:
            raise ValueError("Payload Telegram callback sem chat.id")

        data = callback.get("data")
        if data is None:
            raise ValueError("Payload Telegram callback sem data")

        callback_id = callback.get("id") or payload.get("update_id")
        if callback_id is None:
            raise ValueError("Payload Telegram callback sem id")
        provider_message_id = (
            f"callback:{callback_id}" if callback_id is not None else None
        )

        try:
            return NormalizedMessage(
                provider="telegram",
                provider_chat_id=str(chat_id),
                provider_user_id=str(sender.get("id"))
                if sender.get("id") is not None
                else None,
                provider_user_name=self._telegram_user_name(sender),
                provider_username=str(sender.get("username"))
                if sender.get("username")
                else None,
                provider_message_id=provider_message_id,
                provider_update_id=str(payload.get("update_id"))
                if payload.get("update_id") is not None
                else None,
                event_id=f"telegram:callback:{callback_id}",
                content_type="text",
                text=None,
                callback_query_id=str(callback_id),
                callback_data=str(data).strip(),
                raw_payload=payload,
            )
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def _normalize_whatsapp(self, payload: dict[str, Any]) -> NormalizedMessage:
        if "provider_chat_id" in payload:
            provider_message_id = (
                str(payload.get("provider_message_id"))
                if payload.get("provider_message_id")
                else None
            )
            if not provider_message_id:
                raise ValueError("Payload WhatsApp sem provider_message_id")
            return NormalizedMessage(
                provider="whatsapp",
                provider_chat_id=str(payload["provider_chat_id"]),
                provider_user_id=str(payload.get("provider_user_id"))
                if payload.get("provider_user_id")
                else None,
                provider_user_name=str(payload.get("provider_user_name"))
                if payload.get("provider_user_name")
                else None,
                provider_username=str(payload.get("provider_username"))
                if payload.get("provider_username")
                else None,
                provider_message_id=provider_message_id,
                provider_update_id=str(payload.get("provider_update_id"))
                if payload.get("provider_update_id")
                else None,
                event_id=f"whatsapp:message:{provider_message_id}",
                content_type=payload.get("content_type")
                or payload.get("message_type", "text"),
                text=payload.get("text"),
                callback_data=payload.get("callback_data"),
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

        provider_message_id = str(message.get("id")) if message.get("id") else None
        if not provider_message_id:
            raise ValueError("Payload WhatsApp sem message.id")
        contact = (value.get("contacts") or [{}])[0]
        profile = contact.get("profile") or {}

        return NormalizedMessage(
            provider="whatsapp",
            provider_chat_id=str(message.get("from")),
            provider_user_id=str(message.get("from")),
            provider_user_name=str(profile.get("name"))
            if profile.get("name")
            else None,
            provider_message_id=provider_message_id,
            event_id=f"whatsapp:message:{provider_message_id}",
            content_type=message_type,
            text=text,
            media_file_id=media_file_id,
            raw_payload=payload,
        )

    def _telegram_user_name(self, sender: dict[str, Any]) -> str | None:
        parts = [
            str(sender[field]).strip()
            for field in ("first_name", "last_name")
            if sender.get(field)
        ]
        return " ".join(parts) if parts else None
