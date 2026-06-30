from app.config import Settings
from app.models.normalized_message import NormalizedMessage
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.workers.message_worker import MessageWorker


def test_worker_processes_unknown_text_and_sends_outbound(db):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id="chat-1",
            provider_user_id="user-1",
            provider_message_id="msg-1",
            message_type="text",
            text="Olá",
            raw_payload={},
        ),
    )
    QueueRepository(db).enqueue(message.id, conversation.id)
    settings = Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        telegram_bot_token="",
        debounce_seconds=0,
    )

    result = MessageWorker(db, settings).process_once()
    messages = MessageRepository(db).list_by_conversation(conversation.id)

    assert result["processed"] is True
    assert messages[-1].direction == "outbound"
    assert "Não consegui entender" in messages[-1].normalized_text
