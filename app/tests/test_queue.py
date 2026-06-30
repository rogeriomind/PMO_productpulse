from app.models.normalized_message import NormalizedMessage
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository


def _message(db):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id="chat-1",
            provider_user_id="user-1",
            provider_message_id="msg-1",
            message_type="text",
            text="Cria atividade",
            raw_payload={},
        ),
    )
    return conversation, message


def test_enqueue_and_lock_next(db):
    conversation, message = _message(db)
    queue = QueueRepository(db)
    item = queue.enqueue(message.id, conversation.id)

    locked = queue.lock_next(lock_seconds=30)

    assert locked.id == item.id
    assert locked.status == "processing"
    assert locked.attempts == 1
    assert locked.locked_until is not None


def test_retry_then_lock_again(db):
    conversation, message = _message(db)
    queue = QueueRepository(db)
    item = queue.enqueue(message.id, conversation.id)
    locked = queue.lock_next(lock_seconds=30)

    result = queue.mark_retry(locked.id, "erro temporário", max_attempts=3, delay_seconds=0)
    locked_again = queue.lock_next(lock_seconds=30)

    assert result == "retry"
    assert locked_again.id == item.id
    assert locked_again.attempts == 2


def test_failed_after_max_attempts(db):
    conversation, message = _message(db)
    queue = QueueRepository(db)
    queue.enqueue(message.id, conversation.id)
    locked = queue.lock_next(lock_seconds=30)

    result = queue.mark_retry(locked.id, "erro final", max_attempts=1)

    failed = db.get(type(locked), locked.id)
    assert result == "failed"
    assert failed.status == "failed"
