from sqlalchemy import text

from app.clients.agent_api_client import AgentApiTransientError
from app.config import Settings
from app.contracts.agent_response import AgentResponse
from app.models.normalized_message import NormalizedMessage
from app.repositories.agent_dispatch_repository import AgentDispatchRepository
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.queue_repository import QueueRepository
from app.workers.message_worker import MessageWorker


class FakeAgentApiClient:
    def __init__(
        self, response: AgentResponse | None = None, error: Exception | None = None
    ):
        self.response = response or _agent_response()
        self.error = error
        self.calls = []

    def send_event(self, event):
        self.calls.append(event)
        if self.error:
            raise self.error
        return self.response


class FailingProvider:
    def send_text(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> dict:
        raise RuntimeError("telegram indisponível")


class SuccessProvider:
    def __init__(self):
        self.sent = []
        self.typing = []

    def send_text(
        self, chat_id: str, text: str, reply_markup: dict | None = None
    ) -> dict:
        self.sent.append(
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup}
        )
        return {
            "ok": True,
            "chat_id": chat_id,
            "text": text,
            "reply_markup": reply_markup,
        }

    def send_chat_action(self, chat_id: str, action: str = "typing") -> dict:
        self.typing.append({"chat_id": chat_id, "action": action})
        return {"ok": True, "chat_id": chat_id, "action": action}


def _settings(**overrides):
    values = {
        "app_env": "test",
        "telegram_bot_token": "",
        "debounce_seconds": 0,
        "agent_api_token": "token",
        "agent_api_retry_base_seconds": 0,
        "max_queue_attempts": 2,
    }
    values.update(overrides)
    return Settings(**values)


def _agent_response(message: str = "Resposta da IA", ui: dict | None = None):
    return AgentResponse(
        request_id="request-1",
        correlation_id="correlation-1",
        thread_id="default:telegram:chat-1",
        status="waiting_user_input",
        flow="main_menu",
        step="waiting",
        message=message,
        ui=ui or {"type": "none", "options": []},
    )


def _enqueue(
    db,
    provider_message_id: str,
    *,
    text_value: str | None = "Olá",
    callback_data: str | None = None,
    content_type: str = "text",
    media_file_id: str | None = None,
):
    conversation = ConversationRepository(db).get_or_create(
        "telegram",
        "chat-1",
        "user-1",
        provider_user_name="Rogério",
        provider_username="rogerio",
    )
    event_id = (
        f"telegram:callback:{provider_message_id}"
        if callback_data
        else f"telegram:update:{provider_message_id}"
    )
    message = MessageRepository(db).create_inbound(
        conversation.id,
        NormalizedMessage(
            provider="telegram",
            provider_chat_id="chat-1",
            provider_user_id="user-1",
            provider_user_name="Rogério",
            provider_username="rogerio",
            provider_message_id=provider_message_id,
            provider_update_id=provider_message_id,
            event_id=event_id,
            content_type=content_type,
            text=text_value,
            callback_query_id=provider_message_id if callback_data else None,
            callback_data=callback_data,
            media_file_id=media_file_id,
            raw_payload={},
        ),
    )
    queue = QueueRepository(db).enqueue(message.id, conversation.id)
    return conversation, message, queue


def _messages(db, conversation_id: str):
    return MessageRepository(db).list_by_conversation(conversation_id)


def test_worker_processes_text_and_calls_agent(db):
    conversation, _, _ = _enqueue(db, "1", text_value="sim")
    fake_client = FakeAgentApiClient(
        _agent_response(
            "Escolha uma opção da IA",
            {
                "type": "inline_keyboard",
                "context_id": "status-context-1",
                "options": [
                    {"id": "status", "label": "Status", "callback_data": "menu:status"}
                ],
            },
        )
    )

    result = MessageWorker(db, _settings(), fake_client).process_once()

    messages = _messages(db, conversation.id)
    conversation = ConversationRepository(db).get(conversation.id)
    dispatches = AgentDispatchRepository(db).list_by_conversation(conversation.id)
    assert result["processed"] is True
    assert fake_client.calls[0].message_type == "text"
    assert fake_client.calls[0].content.text == "sim"
    assert messages[-1].direction == "outbound"
    assert (
        messages[-1].raw_payload["reply_markup"]["inline_keyboard"][0][0][
            "callback_data"
        ]
        == "menu:status"
    )
    assert dispatches[0].status == "delivered"
    assert conversation.last_delivered_ui_context_id == "status-context-1"
    assert db.execute(text("SELECT COUNT(*) FROM task_actions")).scalar_one() == 0


def test_worker_processes_callback_and_calls_agent(db):
    _enqueue(db, "callback-1", text_value=None, callback_data="menu:status")
    fake_client = FakeAgentApiClient()

    MessageWorker(db, _settings(), fake_client).process_once()

    event = fake_client.calls[0]
    assert event.message_type == "menu_selection"
    assert event.content.callback_data == "menu:status"


def test_worker_processes_audio_as_transcribed_text(db):
    _enqueue(
        db, "audio-1", text_value=None, content_type="audio", media_file_id="file-1"
    )
    fake_client = FakeAgentApiClient()

    MessageWorker(db, _settings(), fake_client).process_once()

    event = fake_client.calls[0]
    assert event.message_type == "text"
    assert "Criar atividade" in event.content.text
    assert event.metadata.content_type == "audio"
    assert event.metadata.transcribed is True


def test_worker_processes_debounced_messages_once(db):
    conversation, _, _ = _enqueue(db, "debounce-1", text_value="Quero")
    _, _, _ = _enqueue(db, "debounce-2", text_value="status")
    fake_client = FakeAgentApiClient()

    result = MessageWorker(db, _settings(), fake_client).process_once()

    queues = (
        db.execute(text("SELECT status FROM message_queue ORDER BY created_at"))
        .scalars()
        .all()
    )
    assert result["processed"] is True
    assert len(fake_client.calls) == 1
    assert fake_client.calls[0].event_id.startswith("telegram:debounce:")
    assert fake_client.calls[0].content.text == "Quero status"
    assert fake_client.calls[0].metadata.source_message_ids
    assert queues == ["done", "done"]
    assert (
        AgentDispatchRepository(db).list_by_conversation(conversation.id)[0].status
        == "delivered"
    )


def test_worker_reuses_saved_agent_response_after_delivery_failure(db):
    conversation, _, _ = _enqueue(db, "fail-1", text_value="Olá")
    fake_client = FakeAgentApiClient(_agent_response("Resposta persistida"))
    worker = MessageWorker(db, _settings(), fake_client)
    worker.outbound_service.providers["telegram"] = FailingProvider()

    first = worker.process_once()
    dispatch = AgentDispatchRepository(db).list_by_conversation(conversation.id)[0]

    assert first["processed"] is False
    assert first["reason"] == "retry"
    assert dispatch.response_payload["message"] == "Resposta persistida"
    assert dispatch.status == "agent_completed"

    success_provider = SuccessProvider()
    worker.outbound_service.providers["telegram"] = success_provider
    second = worker.process_once()

    assert second["processed"] is True
    assert len(fake_client.calls) == 1
    assert success_provider.sent[0]["text"] == "Resposta persistida"
    assert (
        AgentDispatchRepository(db).list_by_conversation(conversation.id)[0].status
        == "delivered"
    )


def test_worker_retries_agent_failures_without_local_business_fallback(db):
    conversation, _, _ = _enqueue(db, "agent-fail-1", text_value="status")
    fake_client = FakeAgentApiClient(error=AgentApiTransientError("API indisponível"))

    result = MessageWorker(db, _settings(), fake_client).process_once()

    assert result["processed"] is False
    assert result["reason"] == "retry"
    assert not [
        message
        for message in _messages(db, conversation.id)
        if message.direction == "outbound"
    ]


def test_worker_suppresses_stale_read_response_when_newer_input_exists(db):
    conversation, _, _ = _enqueue(
        db, "slow-1", text_value=None, callback_data="menu:status"
    )
    _enqueue(db, "slow-2", text_value="Olá")
    fake_client = FakeAgentApiClient(
        _agent_response("Lista antiga", {"type": "inline_keyboard", "options": []})
    )
    worker = MessageWorker(db, _settings(), fake_client)
    success_provider = SuccessProvider()
    worker.outbound_service.providers["telegram"] = success_provider

    result = worker.process_once()

    dispatch = AgentDispatchRepository(db).list_by_conversation(conversation.id)[0]
    queue_statuses = (
        db.execute(text("SELECT status FROM message_queue ORDER BY created_at"))
        .scalars()
        .all()
    )
    assert result["reason"] == "superseded"
    assert dispatch.status == "superseded"
    assert success_provider.sent == []
    assert queue_statuses == ["done", "pending"]


def test_worker_does_not_suppress_confirmation_response(db):
    conversation, _, _ = _enqueue(db, "write-1", text_value="Criar atividade")
    _enqueue(db, "write-2", text_value="Olá")
    fake_client = FakeAgentApiClient(
        _agent_response(
            "Confirma?",
            {"type": "confirmation", "options": []},
        ).model_copy(
            update={
                "status": "awaiting_confirmation",
                "requires_confirmation": True,
                "confirmation": {"id": "pending-1"},
            }
        )
    )
    worker = MessageWorker(db, _settings(), fake_client)
    success_provider = SuccessProvider()
    worker.outbound_service.providers["telegram"] = success_provider

    result = worker.process_once()

    dispatch = AgentDispatchRepository(db).list_by_conversation(conversation.id)[0]
    assert result["processed"] is True
    assert dispatch.status == "delivered"
    assert success_provider.sent[0]["text"] == "Confirma?"
