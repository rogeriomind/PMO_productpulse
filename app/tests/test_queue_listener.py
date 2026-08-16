from app.config import Settings
from app.workers.queue_listener import QueueListener


def _settings(**overrides):
    values = {
        "app_env": "test",
        "agent_api_token": "token",
        "queue_notify_channel": "pmo_productpulse_queue",
    }
    values.update(overrides)
    return Settings(**values)


class FakeNotify:
    channel = "pmo_productpulse_queue"
    payload = "queue-1"


class FakeConnection:
    def __init__(self, *, notifications=None, error: Exception | None = None):
        self.notifications = notifications or []
        self.error = error
        self.closed = False

    def notifies(self, timeout, stop_after):
        if self.error:
            raise self.error
        yield from self.notifications[:stop_after]

    def close(self):
        self.closed = True


def test_queue_listener_wakes_on_matching_notification():
    listener = QueueListener(_settings())
    listener.connection = FakeConnection(notifications=[FakeNotify()])

    assert listener.wait(0.1) is True


def test_queue_listener_returns_false_on_timeout():
    listener = QueueListener(_settings())
    listener.connection = FakeConnection()

    assert listener.wait(0.1) is False


def test_queue_listener_closes_connection_on_error(monkeypatch):
    listener = QueueListener(_settings())
    connection = FakeConnection(error=RuntimeError("lost connection"))
    listener.connection = connection
    monkeypatch.setattr("app.workers.queue_listener.time.sleep", lambda _: None)

    assert listener.wait(0.1) is True
    assert connection.closed is True
    assert listener.connection is None
