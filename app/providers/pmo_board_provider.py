from typing import Any

import httpx

from app.config import Settings, get_settings
from app.providers.board_provider import BoardProvider, BoardProviderError
from app.providers.pmo_board_auth_provider import PmoBoardAuthProvider


class PmoBoardProvider(BoardProvider):
    def __init__(
        self,
        settings: Settings | None = None,
        auth_provider: PmoBoardAuthProvider | None = None,
        client: httpx.Client | None = None,
    ):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=self.settings.pmo_api_timeout_seconds)
        self.auth_provider = auth_provider or PmoBoardAuthProvider(self.settings, self.client)
        self.base_url = self.settings.pmo_api_url.rstrip("/")

    def _request(self, method: str, path: str, retry_401: bool = True, **kwargs: Any) -> Any:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.update(self.auth_provider.auth_headers())
        response = self.client.request(method, url, headers=headers, **kwargs)
        if response.status_code == 401 and retry_401:
            self.auth_provider.clear_token()
            return self._request(method, path, retry_401=False, **kwargs)
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            raise BoardProviderError(data.get("message") or f"Erro ao chamar PMO Board ({response.status_code})")
        return data

    def set_audit_context(self, conversation_id: str | None = None, message_id: str | None = None) -> None:
        self.auth_provider.set_audit_context(conversation_id, message_id)

    def list_users(self) -> list[dict]:
        data = self._request("GET", "/users")
        return data if isinstance(data, list) else data.get("items", [])

    def list_activities(self, filters: dict | None = None) -> list[dict]:
        data = self._request("GET", "/activities", params=filters or {})
        return data if isinstance(data, list) else data.get("items", [])

    def get_activity(self, activity_id: str) -> dict:
        return self._request("GET", f"/activities/{activity_id}")

    def create_activity(self, payload: dict) -> dict:
        return self._request("POST", "/activities", json=payload)

    def update_activity(self, activity_id: str, payload: dict) -> dict:
        return self._request("PATCH", f"/activities/{activity_id}", json=payload)

    def move_activity(self, activity_id: str, status: str, reason: str | None = None) -> dict:
        payload = {"status": status}
        if reason:
            payload["reason"] = reason
        return self._request("PATCH", f"/activities/{activity_id}/status", json=payload)

    def add_comment(self, activity_id: str, message: str) -> dict:
        return self._request("POST", f"/activities/{activity_id}/comments", json={"message": message})

    def get_alerts(self) -> dict:
        data = self._request("GET", "/alerts")
        if isinstance(data, dict):
            return data
        raise BoardProviderError("Resposta de alertas inválida no PMO Board")
