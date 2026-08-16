from app.config import Settings
from app.database.connection import QueueRecord
from app.models.normalized_message import NormalizedMessage
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.services.queue_notification_service import QueueNotificationService
from app.services.queue_service import QueueService


def _message(
    db,
    *,
    chat_id: str = "chat-1",
    provider_message_id: str = "msg-1",
    update_id: str = "1",
):
    conversation = ConversationRepository(db).get_or_create(
        "telegram", chat_id, "user-1"
    )
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id=chat_id,
            provider_user_id="user-1",
            provider_message_id=provider_message_id,
            provider_update_id=update_id,
            event_id=f"telegram:update:{update_id}",
            content_type="text",
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
    assert locked.queue_locked_at is not None


def test_queue_service_notifies_after_enqueue(db):
    conversation, message = _message(db)
    notified = []

    class SpyNotificationService:
        def notify_new_item(self, queue_id: str):
            assert db.get(QueueRecord, queue_id)
            notified.append(queue_id)

    queue = QueueService(
        QueueRepository(db),
        lock_seconds=30,
        max_attempts=3,
        notification_service=SpyNotificationService(),
    )

    item = queue.enqueue(message.id, conversation.id)

    assert notified == [item.id]


def test_locked_message_is_not_locked_twice(db):
    conversation, message = _message(db)
    queue = QueueRepository(db)
    queue.enqueue(message.id, conversation.id)

    first_lock = queue.lock_next(lock_seconds=30)
    second_lock = queue.lock_next(lock_seconds=30)

    assert first_lock is not None
    assert second_lock is None


def test_active_conversation_lease_does_not_block_other_conversations(db):
    conversation, message = _message(db)
    queue = QueueRepository(db)
    queue.enqueue(message.id, conversation.id)
    first_lock = queue.lock_next(lock_seconds=30)

    same_conversation, same_message = _message(
        db, provider_message_id="msg-2", update_id="2"
    )
    other_conversation, other_message = _message(
        db,
        chat_id="chat-2",
        provider_message_id="msg-3",
        update_id="3",
    )
    same_item = queue.enqueue(same_message.id, same_conversation.id)
    other_item = queue.enqueue(other_message.id, other_conversation.id)
    second_lock = queue.lock_next(lock_seconds=30)
    third_lock = queue.lock_next(lock_seconds=30)

    assert first_lock is not None
    assert same_conversation.id == conversation.id
    assert second_lock.id == other_item.id
    assert third_lock is None
    assert db.get(type(same_item), same_item.id).status == "pending"


def test_retry_then_lock_again(db):
    conversation, message = _message(db)
    queue = QueueRepository(db)
    item = queue.enqueue(message.id, conversation.id)
    locked = queue.lock_next(lock_seconds=30)

    result = queue.mark_retry(
        locked.id, "erro temporário", max_attempts=3, delay_seconds=0
    )
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


def test_postgres_notify_payload_contains_only_queue_id():
    calls = []

    class FakeDialect:
        name = "postgresql"

    class FakeBind:
        dialect = FakeDialect()

    class FakeDb:
        def get_bind(self):
            return FakeBind()

        def execute(self, statement, params):
            calls.append((statement, params))

        def commit(self):
            pass

        def rollback(self):
            pass

    settings = Settings(
        app_env="test",
        agent_api_token="token",
        queue_notify_enabled=True,
        queue_notify_channel="pmo_productpulse_queue",
    )
    QueueNotificationService(FakeDb(), settings).notify_new_item("queue-1")

    assert calls[0][1] == {
        "channel": "pmo_productpulse_queue",
        "payload": "queue-1",
    }


def test_queue_notification_disabled_does_not_touch_database():
    class FakeDb:
        def get_bind(self):
            raise AssertionError("database should not be touched")

    settings = Settings(
        app_env="test", agent_api_token="token", queue_notify_enabled=False
    )

    assert (
        QueueNotificationService(FakeDb(), settings).notify_new_item("queue-1") is False
    )
