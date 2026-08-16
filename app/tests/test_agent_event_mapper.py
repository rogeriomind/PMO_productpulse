from app.config import Settings
from app.integrations.agent_event_mapper import AgentEventMapper
from app.models.normalized_message import NormalizedMessage
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository


def _settings():
    return Settings(app_env="test", agent_api_retry_base_seconds=0)


def _message(db, text: str | None = "Olá", callback_data: str | None = None):
    conversation = ConversationRepository(db).get_or_create(
        "telegram",
        "123",
        "456",
        provider_user_name="Rogério",
        provider_username="rogeriomind",
    )
    provider_message_id = f"cb-{callback_data}" if callback_data else f"msg-{text}"
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id="123",
            provider_user_id="456",
            provider_user_name="Rogério",
            provider_username="rogeriomind",
            provider_message_id=provider_message_id,
            provider_update_id="111",
            event_id=f"telegram:update:{text or callback_data}",
            content_type="text",
            text=text,
            callback_query_id="cb-1" if callback_data else None,
            callback_data=callback_data,
            raw_payload={},
        ),
    )
    return conversation, message


def test_start_generates_welcome(db):
    conversation, message = _message(db, "/start")

    event = AgentEventMapper(_settings()).map(conversation, message, "/start")

    assert event.message_type == "welcome"


def test_human_words_remain_text(db):
    conversation, message = _message(db, "sim")

    event = AgentEventMapper(_settings()).map(conversation, message, "sim")

    assert event.message_type == "text"
    assert event.content.text == "sim"


def test_cancelar_remains_text(db):
    conversation, message = _message(db, "cancelar")

    event = AgentEventMapper(_settings()).map(conversation, message, "cancelar")

    assert event.message_type == "text"


def test_callback_protocol_mappings(db):
    cases = {
        "menu:status": "menu_selection",
        "status:task:1": "task_selection",
        "update:task:1": "task_selection",
        "task:1": "task_selection",
        "confirmation:approve:id": "confirmation",
        "global:cancel": "cancel",
        "global:back": "back",
        "global:reset": "reset",
    }
    mapper = AgentEventMapper(_settings())

    for callback_data, expected in cases.items():
        conversation, message = _message(db, None, callback_data)
        event = mapper.map(conversation, message, None)
        assert event.message_type == expected
        assert event.content.callback_data == callback_data


def test_thread_id_is_deterministic(db):
    conversation, message = _message(db, "Olá")
    mapper = AgentEventMapper(_settings())

    first = mapper.map(conversation, message, "Olá")
    second = mapper.map(conversation, message, "Olá")

    assert first.thread_id == "default:telegram:123"
    assert second.thread_id == first.thread_id
    assert second.request_id == first.request_id


def test_debounce_event_id_is_stable():
    mapper = AgentEventMapper(_settings())

    first = mapper.debounce_event_id(
        "telegram", "conversation-1", ["b", "a"], "texto junto"
    )
    second = mapper.debounce_event_id(
        "telegram", "conversation-1", ["a", "b"], "texto junto"
    )

    assert first == second
    assert first.startswith("telegram:debounce:")
