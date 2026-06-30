from datetime import timedelta

from app.database.connection import utcnow
from app.models.normalized_message import NormalizedMessage
from app.repositories.audit_repository import AuditRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.debounce_repository import DebounceRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.services.audit_service import AuditService
from app.services.debounce_service import DebounceService


def _service(db, seconds=5):
    message_repo = MessageRepository(db)
    queue_repo = QueueRepository(db)
    return DebounceService(
        DebounceRepository(db),
        message_repo,
        queue_repo,
        AuditService(AuditRepository(db)),
        seconds,
    )


def _create_text(db, provider_message_id, text, created_at=None):
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
    if created_at:
        message.created_at = created_at
        db.commit()
    queue_item = QueueRepository(db).enqueue(message.id, conversation.id)
    return conversation, message, queue_item


def test_groups_messages_after_window(db):
    old = utcnow() - timedelta(seconds=10)
    conversation, _, _ = _create_text(db, "m1", "Cria uma atividade", old)
    _create_text(db, "m2", "para Maria", old)

    decision = _service(db, seconds=5).assess_text(conversation.id)

    assert decision.should_wait is False
    assert decision.combined_text == "Cria uma atividade para Maria"
    assert len(decision.queue_ids) == 2


def test_waits_inside_debounce_window(db):
    conversation, message, _ = _create_text(db, "m1", "Cria uma atividade")

    decision = _service(db, seconds=5).assess_text(conversation.id, message.id)

    assert decision.should_wait is True
    assert decision.remaining_seconds > 0


def test_audio_forces_flush_of_pending_text(db):
    old = utcnow() - timedelta(seconds=10)
    conversation, _, queue_item = _create_text(db, "m1", "Cria uma atividade", old)

    decision = _service(db, seconds=5).flush_pending_texts(conversation.id, exclude_queue_id="audio-queue")

    assert decision is not None
    assert decision.combined_text == "Cria uma atividade"
    assert decision.queue_ids == [queue_item.id]
