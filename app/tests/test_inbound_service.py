from app.config import Settings
from app.providers.telegram_provider import TelegramMessageProvider
from app.repositories.audit_repository import AuditRepository
from app.repositories.message_repository import MessageRepository
from app.services.inbound_service import InboundService


def _settings():
    return Settings(
        app_env="test", telegram_bot_token="", agent_api_retry_base_seconds=0
    )


def test_telegram_callback_is_acked_persisted_and_queued(db, monkeypatch):
    acked = []

    def fake_ack(self, callback_query_id: str, text: str | None = None):
        acked.append(callback_query_id)
        return {"ok": True}

    monkeypatch.setattr(TelegramMessageProvider, "answer_callback", fake_ack)
    payload = {
        "update_id": 20,
        "callback_query": {
            "id": "callback-20",
            "from": {"id": 456, "first_name": "Rogério", "username": "rogerio"},
            "message": {"message_id": 12, "chat": {"id": 123}},
            "data": "menu:status",
        },
    }

    result = InboundService(db, _settings()).receive("telegram", payload)

    messages = MessageRepository(db).list_by_conversation(result["conversation_id"])
    audits = AuditRepository(db).list_by_conversation(result["conversation_id"])
    assert result["status"] == "queued"
    assert messages[0].event_id == "telegram:callback:callback-20"
    assert messages[0].callback_data == "menu:status"
    assert acked == ["callback-20"]
    assert any(audit.event_type == "message_queued" for audit in audits)


def test_duplicate_event_is_not_queued_twice(db):
    payload = {
        "update_id": 21,
        "message": {
            "message_id": 21,
            "chat": {"id": 123},
            "from": {"id": 456},
            "text": "Olá",
        },
    }
    service = InboundService(db, _settings())

    first = service.receive("telegram", payload)
    second = service.receive("telegram", payload)

    messages = MessageRepository(db).list_by_conversation(first["conversation_id"])
    assert first["status"] == "queued"
    assert second["status"] == "duplicate"
    assert len(messages) == 1
