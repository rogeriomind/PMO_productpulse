import re
import unicodedata

from app.providers.board_provider import BoardProvider
from app.services.audit_service import AuditService


class BoardContextService:
    def __init__(self, board_provider: BoardProvider, audit_service: AuditService):
        self.board_provider = board_provider
        self.audit_service = audit_service

    def list_users(self, conversation_id: str | None = None, message_id: str | None = None) -> list[dict]:
        self._set_provider_context(conversation_id, message_id)
        self.audit_service.record("pmo_users_fetch_started", "started", conversation_id, message_id)
        try:
            users = self.board_provider.list_users()
            self.audit_service.record(
                "pmo_users_fetch_success",
                "success",
                conversation_id,
                message_id,
                payload={"count": len(users)},
            )
            return users
        except Exception as exc:
            self.audit_service.record("pmo_users_fetch_failed", "failed", conversation_id, message_id, error_message=str(exc))
            raise

    def list_activities(
        self,
        filters: dict | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> list[dict]:
        self._set_provider_context(conversation_id, message_id)
        self.audit_service.record(
            "pmo_activity_search_started",
            "started",
            conversation_id,
            message_id,
            payload={"filters": filters or {}},
        )
        try:
            activities = self.board_provider.list_activities(filters or {})
            self.audit_service.record(
                "pmo_activity_search_success",
                "success",
                conversation_id,
                message_id,
                payload={"count": len(activities)},
            )
            return activities
        except Exception as exc:
            self.audit_service.record(
                "pmo_activity_search_failed",
                "failed",
                conversation_id,
                message_id,
                payload={"filters": filters or {}},
                error_message=str(exc),
            )
            raise

    def get_alerts(self, conversation_id: str | None = None, message_id: str | None = None) -> dict:
        self._set_provider_context(conversation_id, message_id)
        self.audit_service.record("pmo_alerts_fetch_started", "started", conversation_id, message_id)
        try:
            alerts = self.board_provider.get_alerts()
            self.audit_service.record("pmo_alerts_fetch_success", "success", conversation_id, message_id)
            return alerts
        except Exception as exc:
            self.audit_service.record("pmo_alerts_fetch_failed", "failed", conversation_id, message_id, error_message=str(exc))
            raise

    def find_user_in_text(self, input_text: str, conversation_id: str | None = None) -> dict:
        users = self.list_users(conversation_id)
        normalized_text = self._normalize(input_text)
        matches = []
        for user in users:
            name = str(user.get("name") or "")
            normalized_name = self._normalize(name)
            first_name = normalized_name.split(" ")[0] if normalized_name else ""
            if normalized_name and normalized_name in normalized_text:
                matches.append(user)
            elif first_name and re.search(rf"\b{re.escape(first_name)}\b", normalized_text):
                matches.append(user)

        if len(matches) == 1:
            return {"status": "found", "user": matches[0]}
        if len(matches) > 1:
            return {"status": "ambiguous", "users": matches}
        return {"status": "not_found", "users": []}

    def find_activity_in_text(self, input_text: str, conversation_id: str | None = None) -> dict:
        term = self._extract_activity_search(input_text)
        if not term:
            return {"status": "not_found", "term": None, "activities": []}
        activities = self.list_activities({"search": term}, conversation_id)
        if len(activities) == 1:
            return {"status": "found", "term": term, "activity": activities[0]}
        if len(activities) > 1:
            return {"status": "ambiguous", "term": term, "activities": activities}
        return {"status": "not_found", "term": term, "activities": []}

    def _extract_activity_search(self, input_text: str) -> str | None:
        patterns = [
            r"atividade\s+de\s+(.+?)(?:\s+para\s+|\s+como\s+|\s+porque\s+|$)",
            r"atividade\s+(.+?)(?:\s+para\s+|\s+como\s+|\s+porque\s+|$)",
        ]
        for pattern in patterns:
            match = re.search(pattern, input_text, flags=re.IGNORECASE)
            if match:
                term = match.group(1).strip(" .,:;")
                term = re.sub(r"\b(conclu[ií]da|concluido|bloqueada|cancelada|em andamento|em revis[aã]o)\b", "", term, flags=re.IGNORECASE)
                term = term.strip(" .,:;")
                if term:
                    return term
        return None

    def _normalize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.lower())
        return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")

    def _set_provider_context(self, conversation_id: str | None, message_id: str | None) -> None:
        setter = getattr(self.board_provider, "set_audit_context", None)
        if setter:
            setter(conversation_id, message_id)
