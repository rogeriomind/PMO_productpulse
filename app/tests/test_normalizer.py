import pytest

from app.services.inbound_normalizer import InboundNormalizer


def test_normalizes_telegram_text():
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "chat": {"id": 123},
            "from": {"id": 456},
            "text": "Cria uma atividade",
        },
    }

    message = InboundNormalizer().normalize("telegram", payload)

    assert message.provider == "telegram"
    assert message.provider_chat_id == "123"
    assert message.provider_user_id == "456"
    assert message.provider_message_id == "10"
    assert message.message_type == "text"
    assert message.text == "Cria uma atividade"


def test_normalizes_telegram_audio():
    payload = {
        "message": {
            "message_id": 11,
            "chat": {"id": 123},
            "from": {"id": 456},
            "voice": {"file_id": "file-123"},
        },
    }

    message = InboundNormalizer().normalize("telegram", payload)

    assert message.message_type == "audio"
    assert message.media_file_id == "file-123"


def test_invalid_payload_raises_controlled_error():
    with pytest.raises(ValueError):
        InboundNormalizer().normalize("telegram", {"update_id": 1})
