import re
import unicodedata
from typing import Any

from app.models.agent_result import AgentResult
from app.models.board_action import BoardAction


class AgentService:
    def process(self, conversation_id: str, user_id: str | None, input_text: str, context: dict | None = None) -> AgentResult:
        raise NotImplementedError


class MockAgentService(AgentService):
    def process(self, conversation_id: str, user_id: str | None, input_text: str, context: dict | None = None) -> AgentResult:
        text = self._normalize(input_text)

        if self._has_any(text, ["cria", "criar", "nova atividade"]):
            return self._result(
                "create_task",
                True,
                "Confirma a criação da atividade?",
                "create_activity",
                {
                    "title": "Atividade extraída da mensagem",
                    "description": "Atividade criada via agente PMO",
                    "status": "TODO",
                    "priority": "MEDIUM",
                    "assigneeName": None,
                    "dueDate": None,
                    "tags": ["PMO"],
                },
                0.85,
            )

        if self._has_any(text, ["atrasadas", "alertas", "risco", "bloqueadas", "sem responsavel"]):
            return self._result("query_alerts", False, "Vou consultar os alertas do board.", "query_alerts", {}, 0.82)

        if self._has_any(text, ["quais atividades", "pendencias", "minhas atividades"]):
            return self._result("query_tasks", False, "Vou consultar as atividades do board.", "query_activities", {}, 0.82)

        if self._has_any(text, ["muda prazo", "alterar data", "mudar data"]):
            return self._result(
                "change_due_date",
                True,
                "Confirma a alteração de prazo?",
                "update_activity",
                {"activityId": None, "fields": {"dueDate": None}},
                0.78,
                ["activityId", "dueDate"],
            )

        if self._has_any(text, ["concluida", "concluido", "em andamento", "bloqueada", "cancelada", "em revisao", "a fazer"]):
            status = self._status_from_text(text)
            return self._result(
                "move_activity",
                True,
                "Confirma mover a atividade?",
                "move_activity",
                {"activityId": None, "status": status, "reason": self._reason_from_text(input_text)},
                0.8,
                ["activityId"] if not status else ["activityId"],
            )

        if self._has_any(text, ["comentario", "comenta", "adiciona comentario", "registrar impedimento", "registra impedimento"]):
            return self._result(
                "add_comment",
                True,
                "Confirma adicionar o comentário?",
                "add_comment",
                {"activityId": None, "message": input_text},
                0.75,
                ["activityId"],
            )

        if self._has_any(text, ["atualiza", "alterar", "edita"]):
            return self._result(
                "update_task",
                True,
                "Confirma a atualização da atividade?",
                "update_activity",
                {"activityId": None, "fields": {"description": input_text}},
                0.76,
                ["activityId"],
            )

        return self._result(
            "unknown",
            False,
            "Não consegui entender a ação. Pode mandar de forma mais objetiva?",
            "unknown",
            {},
            0.2,
        )

    def _result(
        self,
        intent: str,
        requires_confirmation: bool,
        response_text: str,
        action_type: str,
        payload: dict[str, Any],
        confidence: float,
        missing_fields: list[str] | None = None,
    ) -> AgentResult:
        return AgentResult(
            intent=intent,
            confidence=confidence,
            requires_confirmation=requires_confirmation,
            response_text=response_text,
            board_action=BoardAction(type=action_type, payload=payload),
            missing_fields=missing_fields or [],
        )

    def _normalize(self, text: str) -> str:
        decomposed = unicodedata.normalize("NFD", text.lower())
        return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")

    def _has_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    def _status_from_text(self, text: str) -> str | None:
        if "a fazer" in text:
            return "TODO"
        if "em andamento" in text:
            return "IN_PROGRESS"
        if "bloqueada" in text:
            return "BLOCKED"
        if "em revisao" in text:
            return "IN_REVIEW"
        if "concluida" in text or "concluido" in text:
            return "DONE"
        if "cancelada" in text:
            return "CANCELED"
        return None

    def _reason_from_text(self, text: str) -> str | None:
        match = re.search(r"\bporque\b(.+)$", text, flags=re.IGNORECASE)
        if not match:
            return None
        return match.group(1).strip().capitalize()
