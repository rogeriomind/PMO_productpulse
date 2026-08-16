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


def _service(
    db,
    seconds=5,
    max_seconds=10,
    *,
    adaptive_enabled=False,
    min_seconds=0.7,
    increment_seconds=0.4,
    max_messages=8,
    adaptive_max_seconds=2.5,
):
    message_repo = MessageRepository(db)
    queue_repo = QueueRepository(db)
    return DebounceService(
        DebounceRepository(db),
        message_repo,
        queue_repo,
        AuditService(AuditRepository(db)),
        seconds,
        max_seconds,
        adaptive_enabled=adaptive_enabled,
        debounce_min_seconds=min_seconds,
        debounce_increment_seconds=increment_seconds,
        debounce_max_messages=max_messages,
        adaptive_max_seconds=adaptive_max_seconds,
    )


def _create_text(db, provider_message_id, text, created_at=None):
    conversation = ConversationRepository(db).get_or_create(
        "telegram", "chat-1", "user-1"
    )
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id="chat-1",
            provider_user_id="user-1",
            provider_message_id=provider_message_id,
            provider_update_id=provider_message_id,
            event_id=f"telegram:update:{provider_message_id}",
            content_type="text",
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
    assert len(decision.message_ids) == 2


def test_waits_inside_debounce_window(db):
    conversation, message, _ = _create_text(db, "m1", "Cria uma atividade")

    decision = _service(db, seconds=5).assess_text(conversation.id, message.id)

    assert decision.should_wait is True
    assert decision.remaining_seconds > 0


def test_max_debounce_window_flushes_even_after_recent_fragment(db):
    first = utcnow() - timedelta(seconds=2.5)
    recent = utcnow() - timedelta(seconds=0.2)
    conversation, _, _ = _create_text(db, "m1", "Cria uma atividade", first)
    _create_text(db, "m2", "para revisar a integração", recent)

    decision = _service(db, seconds=1, max_seconds=2).assess_text(conversation.id)

    assert decision.should_wait is False
    assert decision.combined_text == "Cria uma atividade para revisar a integração"


def test_recent_fragments_wait_until_base_window(db):
    first = utcnow() - timedelta(seconds=0.6)
    recent = utcnow() - timedelta(seconds=0.2)
    conversation, _, _ = _create_text(db, "m1", "Cria uma tarefa", first)
    _create_text(db, "m2", "para amanhã", recent)

    decision = _service(db, seconds=1, max_seconds=2).assess_text(conversation.id)

    assert decision.should_wait is True
    assert 0 < decision.remaining_seconds <= 1


def test_adaptive_single_message_uses_minimum_window(db):
    conversation, message, _ = _create_text(db, "adaptive-1", "Status")

    decision = _service(db, adaptive_enabled=True).assess_text(
        conversation.id, message.id
    )

    assert decision.should_wait is True
    assert 0 < decision.remaining_seconds <= 0.7


def test_adaptive_window_extends_with_fragments(db):
    first = utcnow() - timedelta(seconds=0.8)
    recent = utcnow() - timedelta(seconds=0.1)
    conversation, _, _ = _create_text(db, "adaptive-2", "Cria tarefa", first)
    _create_text(db, "adaptive-3", "para sexta", recent)

    decision = _service(db, adaptive_enabled=True).assess_text(conversation.id)

    assert decision.should_wait is True
    assert 0.7 < decision.remaining_seconds <= 1.1


def test_adaptive_max_messages_flushes_immediately(db):
    conversation = None
    for index in range(8):
        conversation, _, _ = _create_text(db, f"adaptive-max-{index}", f"parte {index}")

    decision = _service(db, adaptive_enabled=True, max_messages=8).assess_text(
        conversation.id
    )

    assert decision.should_wait is False
    assert decision.combined_text.startswith("parte 0 parte 1")


def test_audio_forces_flush_of_pending_text(db):
    old = utcnow() - timedelta(seconds=10)
    conversation, _, queue_item = _create_text(db, "m1", "Cria uma atividade", old)

    decision = _service(db, seconds=5).flush_pending_texts(
        conversation.id, exclude_queue_id="audio-queue"
    )

    assert decision is not None
    assert decision.combined_text == "Cria uma atividade"
    assert decision.queue_ids == [queue_item.id]
