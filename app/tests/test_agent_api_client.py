import httpx
import pytest

from app.clients.agent_api_client import (
    AgentApiAuthenticationError,
    AgentApiClient,
    AgentApiContractError,
    AgentApiTimeoutError,
    AgentApiTransientError,
    AgentApiValidationError,
)
from app.config import Settings
from app.contracts.agent_event import (
    AgentEvent,
    AgentEventContent,
    AgentEventMetadata,
    AgentEventUser,
)


def _settings(**overrides):
    values = {
        "app_env": "test",
        "agent_api_url": "http://agent.local",
        "agent_api_token": "secret-token",
        "agent_api_retry_base_seconds": 0,
        "agent_api_retry_attempts": 3,
    }
    values.update(overrides)
    return Settings(**values)


def _event():
    return AgentEvent(
        event_id="telegram:update:1",
        request_id="request-1",
        correlation_id="correlation-1",
        thread_id="default:telegram:123",
        tenant_id="default",
        channel="telegram",
        message_type="text",
        user=AgentEventUser(id="456", name="Rogério", username="rogeriomind"),
        content=AgentEventContent(text="Olá"),
        metadata=AgentEventMetadata(
            chat_id="123",
            message_id="987",
            provider_update_id="1",
            timezone="America/Sao_Paulo",
            content_type="text",
            source_message_ids=["local-1"],
        ),
    )


def _response(status_code=200, **overrides):
    payload = {
        "request_id": "request-1",
        "correlation_id": "correlation-1",
        "thread_id": "default:telegram:123",
        "status": "waiting_user_input",
        "flow": "main_menu",
        "step": "waiting",
        "message": "Olá",
        "ui": {"type": "none", "options": []},
        "data": {},
        "requires_confirmation": False,
        "confirmation": None,
        "error": None,
    }
    payload.update(overrides)
    return httpx.Response(status_code, json=payload)


def test_sends_payload_and_headers():
    requests = []

    def handler(request):
        requests.append(request)
        return _response()

    transport = httpx.MockTransport(handler)
    client = AgentApiClient(_settings(), httpx.Client(transport=transport))

    response = client.send_event(_event())

    request = requests[0]
    assert response.message == "Olá"
    assert str(request.url) == "http://agent.local/v2/agent/events"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["X-Request-ID"] == "request-1"
    assert request.headers["X-Correlation-ID"] == "correlation-1"
    assert b'"event_id":"telegram:update:1"' in request.content


def test_retries_500_and_preserves_payload():
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(500, json={"error": "temporary"})
        return _response()

    client = AgentApiClient(
        _settings(), httpx.Client(transport=httpx.MockTransport(handler))
    )

    client.send_event(_event())

    assert len(requests) == 2
    assert requests[0].content == requests[1].content
    assert requests[0].headers["X-Request-ID"] == requests[1].headers["X-Request-ID"]


def test_retries_429():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return (
            httpx.Response(429, json={"error": "rate"}) if calls == 1 else _response()
        )

    AgentApiClient(
        _settings(), httpx.Client(transport=httpx.MockTransport(handler))
    ).send_event(_event())

    assert calls == 2


def test_does_not_retry_400():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad"})

    with pytest.raises(AgentApiValidationError):
        AgentApiClient(
            _settings(), httpx.Client(transport=httpx.MockTransport(handler))
        ).send_event(_event())

    assert calls == 1


def test_does_not_retry_401():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"error": "auth"})

    with pytest.raises(AgentApiAuthenticationError):
        AgentApiClient(
            _settings(), httpx.Client(transport=httpx.MockTransport(handler))
        ).send_event(_event())

    assert calls == 1


def test_timeout_raises_after_retries():
    calls = 0

    def handler(request):
        nonlocal calls
        calls += 1
        raise httpx.TimeoutException("timeout")

    with pytest.raises(AgentApiTimeoutError):
        AgentApiClient(
            _settings(agent_api_retry_attempts=2),
            httpx.Client(transport=httpx.MockTransport(handler)),
        ).send_event(_event())

    assert calls == 2


def test_invalid_response_contract():
    def handler(request):
        return httpx.Response(200, json={"message": "sem campos obrigatórios"})

    with pytest.raises(AgentApiContractError):
        AgentApiClient(
            _settings(), httpx.Client(transport=httpx.MockTransport(handler))
        ).send_event(_event())


def test_replay_409_with_valid_payload():
    def handler(request):
        return _response(status_code=409, message="Replay")

    response = AgentApiClient(
        _settings(), httpx.Client(transport=httpx.MockTransport(handler))
    ).send_event(_event())

    assert response.message == "Replay"


def test_token_does_not_appear_in_logs(caplog):
    def handler(request):
        return httpx.Response(200, json={"invalid": True})

    with pytest.raises(AgentApiContractError):
        AgentApiClient(
            _settings(), httpx.Client(transport=httpx.MockTransport(handler))
        ).send_event(_event())

    assert "secret-token" not in caplog.text


def test_5xx_exhaustion_raises_transient():
    def handler(request):
        return httpx.Response(503, json={"error": "down"})

    with pytest.raises(AgentApiTransientError):
        AgentApiClient(
            _settings(agent_api_retry_attempts=1),
            httpx.Client(transport=httpx.MockTransport(handler)),
        ).send_event(_event())
