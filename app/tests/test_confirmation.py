from app.repositories.audit_repository import AuditRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.task_action_repository import TaskActionRepository
from app.services.audit_service import AuditService
from app.services.confirmation_service import ConfirmationService


def _service(db):
    return ConfirmationService(TaskActionRepository(db), AuditService(AuditRepository(db)))


def test_create_pending_action(db):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")
    action = _service(db).create_pending_action(
        conversation.id,
        "user-1",
        "create_task",
        {"type": "create_activity", "payload": {"title": "Teste"}},
    )

    assert action.status == "pending_confirmation"
    assert action.confirmation_token


def test_confirm_action(db):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")
    service = _service(db)
    service.create_pending_action(conversation.id, "user-1", "create_task", {"type": "create_activity", "payload": {}})

    action = service.confirm_latest(conversation.id)

    assert action.status == "confirmed"
    assert action.confirmed_at is not None


def test_cancel_action(db):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")
    service = _service(db)
    service.create_pending_action(conversation.id, "user-1", "create_task", {"type": "create_activity", "payload": {}})

    action = service.cancel_latest(conversation.id)

    assert action.status == "canceled"


def test_does_not_confirm_when_no_pending_action(db):
    conversation = ConversationRepository(db).get_or_create("telegram", "chat-1", "user-1")

    action = _service(db).confirm_latest(conversation.id)

    assert action is None
