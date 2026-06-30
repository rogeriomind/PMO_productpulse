import httpx

from app.config import Settings
from app.providers.pmo_board_auth_provider import PmoBoardAuthProvider
from app.providers.pmo_board_provider import PmoBoardProvider


def _settings():
    return Settings(
        app_env="test",
        database_url="sqlite+pysqlite:///:memory:",
        pmo_api_url="http://pmo.test/api",
        pmo_api_email="rogerio@pmo.local",
        pmo_api_password="123456",
    )


def test_login_and_list_users():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"token": "jwt-1", "user": {"id": "u1"}})
        if request.url.path == "/api/users":
            assert request.headers["Authorization"] == "Bearer jwt-1"
            return httpx.Response(200, json=[{"id": "u1", "name": "Maria"}])
        return httpx.Response(404, json={"message": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = _settings()
    auth = PmoBoardAuthProvider(settings, client)
    provider = PmoBoardProvider(settings, auth, client)

    assert provider.list_users() == [{"id": "u1", "name": "Maria"}]


def test_activity_methods_and_alerts():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/auth/login":
            return httpx.Response(200, json={"token": "jwt-1"})
        if request.url.path == "/api/activities" and request.method == "GET":
            return httpx.Response(200, json=[{"id": "a1", "title": "Integração"}])
        if request.url.path == "/api/activities" and request.method == "POST":
            return httpx.Response(200, json={"id": "a2", "title": "Nova"})
        if request.url.path == "/api/activities/a1" and request.method == "PATCH":
            return httpx.Response(200, json={"id": "a1", "priority": "HIGH"})
        if request.url.path == "/api/activities/a1/status":
            return httpx.Response(200, json={"id": "a1", "status": "DONE"})
        if request.url.path == "/api/activities/a1/comments":
            return httpx.Response(200, json={"id": "c1"})
        if request.url.path == "/api/alerts":
            return httpx.Response(200, json={"overdue": [], "atRisk": []})
        return httpx.Response(404, json={"message": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = _settings()
    auth = PmoBoardAuthProvider(settings, client)
    provider = PmoBoardProvider(settings, auth, client)

    assert provider.list_activities({"search": "Integração"})[0]["id"] == "a1"
    assert provider.create_activity({"title": "Nova"})["id"] == "a2"
    assert provider.update_activity("a1", {"priority": "HIGH"})["priority"] == "HIGH"
    assert provider.move_activity("a1", "DONE")["status"] == "DONE"
    assert provider.add_comment("a1", "ok")["id"] == "c1"
    assert provider.get_alerts()["overdue"] == []
    assert ("GET", "/api/activities") in calls


def test_retries_login_after_401():
    state = {"login_count": 0, "users_count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/auth/login":
            state["login_count"] += 1
            return httpx.Response(200, json={"token": f"jwt-{state['login_count']}"})
        if request.url.path == "/api/users":
            state["users_count"] += 1
            if state["users_count"] == 1:
                return httpx.Response(401, json={"message": "expired"})
            assert request.headers["Authorization"] == "Bearer jwt-2"
            return httpx.Response(200, json=[{"id": "u1"}])
        return httpx.Response(404, json={"message": "not found"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = _settings()
    auth = PmoBoardAuthProvider(settings, client)
    provider = PmoBoardProvider(settings, auth, client)

    assert provider.list_users() == [{"id": "u1"}]
    assert state["login_count"] == 2
