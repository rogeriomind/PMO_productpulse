import pytest

from app.services.inbound_normalizer import InboundNormalizer


def test_normalizes_telegram_text():
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": 123},
            "from": {
                "id": 456,
                "first_name": "Rogério",
                "last_name": "Silva",
                "username": "rogeriomind",
            },
            "text": "Cria uma atividade",
        },
    }

    message = InboundNormalizer().normalize("telegram", payload)

    assert message.provider == "telegram"
    assert message.provider_chat_id == "123"
    assert message.provider_user_id == "456"
    assert message.provider_user_name == "Rogério Silva"
    assert message.provider_username == "rogeriomind"
    assert message.provider_message_id == "10"
    assert message.provider_update_id == "1"
    assert message.event_id == "telegram:update:1"
    assert message.message_type == "text"
    assert message.content_type == "text"
    assert message.text == "Cria uma atividade"


def test_normalizes_telegram_audio():
    payload = {
        "update_id": 3,
        "message": {
            "message_id": 11,
            "chat": {"id": 123},
            "from": {"id": 456},
            "voice": {"file_id": "file-123"},
        },
    }

    message = InboundNormalizer().normalize("telegram", payload)

    assert message.content_type == "audio"
    assert message.media_file_id == "file-123"
    assert message.event_id == "telegram:update:3"


def test_normalizes_telegram_callback_query_as_text():
    payload = {
        "update_id": 2,
        "callback_query": {
            "id": "callback-1",
            "from": {"id": 456},
            "message": {"message_id": 12, "chat": {"id": 123}},
            "data": "menu:status",
        },
    }

    message = InboundNormalizer().normalize("telegram", payload)

    assert message.provider == "telegram"
    assert message.provider_chat_id == "123"
    assert message.provider_user_id == "456"
    assert message.provider_message_id == "callback:callback-1"
    assert message.provider_update_id == "2"
    assert message.event_id == "telegram:callback:callback-1"
    assert message.content_type == "text"
    assert message.text is None
    assert message.callback_query_id == "callback-1"
    assert message.callback_data == "menu:status"


def test_normalizes_whatsapp_text():
    payload = {
        "provider_chat_id": "5511999999999",
        "provider_user_id": "5511999999999",
        "provider_user_name": "Rogério",
        "provider_message_id": "wamid-1",
        "text": "Olá",
    }

    message = InboundNormalizer().normalize("whatsapp", payload)

    assert message.provider == "whatsapp"
    assert message.provider_chat_id == "5511999999999"
    assert message.provider_user_name == "Rogério"
    assert message.event_id == "whatsapp:message:wamid-1"
    assert message.content_type == "text"


def test_invalid_payload_raises_controlled_error():
    with pytest.raises(ValueError):
        InboundNormalizer().normalize("telegram", {"update_id": 1})
