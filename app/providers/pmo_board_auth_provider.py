import httpx

from app.config import Settings, get_settings
from app.providers.board_provider import BoardProviderError
from app.services.audit_service import AuditService


class PmoBoardAuthProvider:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
        audit_service: AuditService | None = None,
    ):
        self.settings = settings or get_settings()
        self.client = client or httpx.Client(timeout=self.settings.pmo_api_timeout_seconds)
        self.audit_service = audit_service
        self._conversation_id: str | None = None
        self._message_id: str | None = None
        self._token: str | None = None

    def set_audit_context(self, conversation_id: str | None = None, message_id: str | None = None) -> None:
        self._conversation_id = conversation_id
        self._message_id = message_id

    def clear_token(self) -> None:
        self._token = None

    def get_token(self) -> str:
        if self._token:
            return self._token
        url = f"{self.settings.pmo_api_url.rstrip('/')}/auth/login"
        self._audit("pmo_auth_started", "started")
        response = self.client.post(
            url,
            json={"email": self.settings.pmo_api_email, "password": self.settings.pmo_api_password},
        )
        data = response.json() if response.content else {}
        if response.status_code >= 400:
            message = data.get("message") or "Falha ao autenticar no PMO Board"
            self._audit("pmo_auth_failed", "failed", error_message=message)
            raise BoardProviderError(message)
        token = data.get("token")
        if not token:
            message = "PMO Board não retornou token de autenticação"
            self._audit("pmo_auth_failed", "failed", error_message=message)
            raise BoardProviderError(message)
        self._token = token
        self._audit("pmo_auth_success", "success", payload={"user": data.get("user")})
        return token

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get_token()}"}

    def _audit(self, event_type: str, status: str, payload: dict | None = None, error_message: str | None = None) -> None:
        if not self.audit_service:
            return
        self.audit_service.record(
            event_type,
            status,
            conversation_id=self._conversation_id,
            message_id=self._message_id,
            payload=payload,
            error_message=error_message,
        )
