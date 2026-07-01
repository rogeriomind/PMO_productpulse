from app.config import Settings
from app.models.normalized_message import NormalizedMessage
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.workers.message_worker import MessageWorker


def _settings():
    return Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        telegram_bot_token="",
        debounce_seconds=0,
    )


def _enqueue_text(db, provider_message_id: str, text: str):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id="chat-1",
            provider_user_id="user-1",
            provider_message_id=provider_message_id,
            message_type="text",
            text=text,
            raw_payload={},
        ),
    )
    QueueRepository(db).enqueue(message.id, conversation.id)
    return conversation, message


def test_worker_sends_telegram_menu_for_inbound_message(db):
    conversation, _ = _enqueue_text(db, "msg-1", "Olá")

    result = MessageWorker(db, _settings()).process_once()
    messages = MessageRepository(db).list_by_conversation(conversation.id)

    assert result["processed"] is True
    assert messages[-1].direction == "outbound"
    assert "Escolha uma opção" in messages[-1].normalized_text
    assert messages[-1].raw_payload["reply_markup"]["inline_keyboard"][0][0]["text"] == "Status"


def test_worker_returns_status_mock_for_menu_callback(db):
    conversation, _ = _enqueue_text(db, "callback-1", "menu_status")

    result = MessageWorker(db, _settings()).process_once()
    messages = MessageRepository(db).list_by_conversation(conversation.id)

    assert result["processed"] is True
    assert messages[-1].direction == "outbound"
    assert "Status mockado" in messages[-1].normalized_text


def test_worker_returns_task_mock_for_typed_menu_option(db):
    conversation, _ = _enqueue_text(db, "msg-2", "Criação/Atualização Tarefa")

    result = MessageWorker(db, _settings()).process_once()
    messages = MessageRepository(db).list_by_conversation(conversation.id)

    assert result["processed"] is True
    assert messages[-1].direction == "outbound"
    assert "Fluxo mockado de criação/atualização de tarefa" in messages[-1].normalized_text


def test_worker_returns_question_mock_for_typed_menu_option(db):
    conversation, _ = _enqueue_text(db, "msg-3", "Duvida")

    result = MessageWorker(db, _settings()).process_once()
    messages = MessageRepository(db).list_by_conversation(conversation.id)

    assert result["processed"] is True
    assert messages[-1].direction == "outbound"
    assert "Fluxo mockado de dúvida" in messages[-1].normalized_text
