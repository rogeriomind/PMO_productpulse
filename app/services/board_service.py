import copy
import re
from datetime import date, timedelta
from typing import Any

from app.database.connection import TaskActionRecord
from app.models.agent_result import AgentResult
from app.providers.board_provider import BoardProvider, BoardProviderError
from app.services.audit_service import AuditService
from app.services.board_context_service import BoardContextService
from app.services.confirmation_service import ConfirmationService


class BoardService:
    def __init__(
        self,
        board_provider: BoardProvider,
        context_service: BoardContextService,
        confirmation_service: ConfirmationService,
        audit_service: AuditService,
    ):
        self.board_provider = board_provider
        self.context_service = context_service
        self.confirmation_service = confirmation_service
        self.audit_service = audit_service

    def handle_agent_result(
        self,
        conversation_id: str,
        user_id: str | None,
        input_text: str,
        agent_result: AgentResult,
    ) -> str:
        action_type = agent_result.board_action.type
        if action_type == "unknown":
            return agent_result.response_text
        if action_type == "query_activities":
            return self._query_activities(conversation_id)
        if action_type == "query_alerts":
            return self._query_alerts(conversation_id)

        prepared = self._prepare_action(conversation_id, input_text, agent_result)
        if prepared.get("error"):
            return prepared["error"]

        action = self.confirmation_service.create_pending_action(
            conversation_id=conversation_id,
            user_id=user_id,
            intent=agent_result.intent,
            action_payload=prepared,
        )
        return self._confirmation_message(action)

    def execute_confirmed_action(self, action: TaskActionRecord) -> str:
        if action.status != "confirmed":
            return "Ação ainda não confirmada. Nenhuma alteração foi feita no board."

        self._set_provider_context(action.conversation_id)
        action_type = action.action_payload.get("type")
        payload = copy.deepcopy(action.action_payload.get("payload") or {})
        try:
            if action_type == "create_activity":
                self.audit_service.record("pmo_activity_create_started", "started", action.conversation_id, payload=payload)
                result = self.board_provider.create_activity(self._clean_board_payload(payload))
                self.audit_service.record("pmo_activity_create_success", "success", action.conversation_id, payload=result)
                self.confirmation_service.repository.mark_executed(action.id, result)
                return "Atividade criada no board com sucesso."

            if action_type == "update_activity":
                activity_id = payload.pop("activityId")
                fields = self._clean_board_payload(payload.get("fields") or payload)
                self.audit_service.record("pmo_activity_update_started", "started", action.conversation_id, payload=fields)
                result = self.board_provider.update_activity(activity_id, fields)
                self.audit_service.record("pmo_activity_update_success", "success", action.conversation_id, payload=result)
                self.confirmation_service.repository.mark_executed(action.id, result)
                return "Atividade atualizada no board com sucesso."

            if action_type == "move_activity":
                activity_id = payload["activityId"]
                status = payload["status"]
                reason = payload.get("reason")
                self.audit_service.record("pmo_activity_status_change_started", "started", action.conversation_id, payload=payload)
                result = self.board_provider.move_activity(activity_id, status, reason)
                if status == "BLOCKED" and reason:
                    comment = f"Bloqueio registrado via agente PMO: {reason}."
                    self.audit_service.record("pmo_comment_create_started", "started", action.conversation_id, payload={"message": comment})
                    self.board_provider.add_comment(activity_id, comment)
                    self.audit_service.record("pmo_comment_create_success", "success", action.conversation_id)
                self.audit_service.record("pmo_activity_status_change_success", "success", action.conversation_id, payload=result)
                self.confirmation_service.repository.mark_executed(action.id, result)
                return "Atividade movida no board com sucesso."

            if action_type == "add_comment":
                activity_id = payload["activityId"]
                message = payload["message"]
                self.audit_service.record("pmo_comment_create_started", "started", action.conversation_id, payload=payload)
                result = self.board_provider.add_comment(activity_id, message)
                self.audit_service.record("pmo_comment_create_success", "success", action.conversation_id, payload=result)
                self.confirmation_service.repository.mark_executed(action.id, result)
                return "Comentário adicionado no board com sucesso."

            raise BoardProviderError("Tipo de ação não suportado")
        except Exception as exc:
            self.confirmation_service.repository.mark_failed(action.id, str(exc))
            failed_event = {
                "create_activity": "pmo_activity_create_failed",
                "update_activity": "pmo_activity_update_failed",
                "move_activity": "pmo_activity_status_change_failed",
                "add_comment": "pmo_comment_create_failed",
            }.get(action_type, "pmo_activity_update_failed")
            self.audit_service.record(failed_event, "failed", action.conversation_id, payload=payload, error_message=str(exc))
            return f"Não consegui executar a ação: {str(exc).lower()}"

    def _prepare_action(self, conversation_id: str, input_text: str, agent_result: AgentResult) -> dict:
        action_type = agent_result.board_action.type
        payload = copy.deepcopy(agent_result.board_action.payload)

        if action_type == "create_activity":
            prepared_payload = self._prepare_create_payload(conversation_id, input_text, payload)
            if prepared_payload.get("assigneeAmbiguity"):
                return {
                    "error": (
                        "Encontrei mais de uma pessoa: "
                        f"{prepared_payload['assigneeAmbiguity']}. Pode informar o responsável completo?"
                    )
                }
            return {"type": action_type, "payload": prepared_payload}

        if action_type == "update_activity":
            activity = self.context_service.find_activity_in_text(input_text, conversation_id)
            if activity["status"] == "ambiguous":
                return {"error": self._ambiguous_activity_message(activity["activities"])}
            if activity["status"] != "found":
                return {"error": "Não encontrei a atividade no board. Pode informar um nome mais específico?"}
            payload["activityId"] = activity["activity"].get("id")
            fields = payload.get("fields") or {}
            if agent_result.intent == "change_due_date":
                due_date = self._extract_due_date(input_text)
                if not due_date:
                    return {"error": "Informe o novo prazo da atividade para eu montar a alteração."}
                fields["dueDate"] = due_date
            payload["fields"] = fields
            payload["activityTitle"] = self._activity_title(activity["activity"])
            return {"type": action_type, "payload": payload}

        if action_type == "move_activity":
            activity = self.context_service.find_activity_in_text(input_text, conversation_id)
            if activity["status"] == "ambiguous":
                return {"error": self._ambiguous_activity_message(activity["activities"])}
            if activity["status"] != "found":
                return {"error": "Não encontrei a atividade no board. Pode informar um nome mais específico?"}
            if not payload.get("status"):
                return {"error": "Informe o novo status da atividade."}
            payload["activityId"] = activity["activity"].get("id")
            payload["activityTitle"] = self._activity_title(activity["activity"])
            return {"type": action_type, "payload": payload}

        if action_type == "add_comment":
            activity = self.context_service.find_activity_in_text(input_text, conversation_id)
            if activity["status"] == "ambiguous":
                return {"error": self._ambiguous_activity_message(activity["activities"])}
            if activity["status"] != "found":
                return {"error": "Não encontrei a atividade no board. Pode informar um nome mais específico?"}
            payload["activityId"] = activity["activity"].get("id")
            payload["activityTitle"] = self._activity_title(activity["activity"])
            return {"type": action_type, "payload": payload}

        return {"error": "Tipo de ação não suportado."}

    def _prepare_create_payload(self, conversation_id: str, input_text: str, payload: dict) -> dict:
        user_match = self.context_service.find_user_in_text(input_text, conversation_id)
        if user_match["status"] == "found":
            user = user_match["user"]
            payload["assigneeId"] = user.get("id")
            payload["assigneeName"] = user.get("name")
        elif user_match["status"] == "ambiguous":
            names = ", ".join(str(user.get("name")) for user in user_match["users"][:5])
            payload["assigneeAmbiguity"] = names

        payload["priority"] = self._extract_priority(input_text) or payload.get("priority") or "MEDIUM"
        payload["dueDate"] = self._extract_due_date(input_text) or payload.get("dueDate")
        title = self._extract_create_title(input_text, payload.get("assigneeName"))
        payload["title"] = title or payload.get("title") or "Atividade extraída da mensagem"
        return payload

    def _query_activities(self, conversation_id: str) -> str:
        activities = self.context_service.list_activities({}, conversation_id)
        if not activities:
            return "Não encontrei atividades no board."
        lines = ["Atividades encontradas:"]
        for index, activity in enumerate(activities[:10], start=1):
            lines.append(
                f"{index}. {self._activity_title(activity)} — {activity.get('status', 'sem status')} — {self._assignee_name(activity)}"
            )
        return "\n".join(lines)

    def _query_alerts(self, conversation_id: str) -> str:
        alerts = self.context_service.get_alerts(conversation_id)
        overdue = alerts.get("overdue") or []
        if overdue:
            lines = ["Atividades atrasadas encontradas:"]
            for index, activity in enumerate(overdue[:10], start=1):
                lines.append(
                    f"{index}. {self._activity_title(activity)} — {self._assignee_name(activity)} — {activity.get('dueDate', 'sem prazo')}"
                )
            return "\n".join(lines)
        counts = {key: len(value) for key, value in alerts.items() if isinstance(value, list) and value}
        if counts:
            summary = ", ".join(f"{key}: {value}" for key, value in counts.items())
            return f"Não há atividades atrasadas. Outros alertas: {summary}."
        return "Não há atividades atrasadas no momento."

    def _confirmation_message(self, action: TaskActionRecord) -> str:
        action_type = action.action_payload.get("type")
        payload = action.action_payload.get("payload") or {}
        if action_type == "create_activity":
            if payload.get("assigneeAmbiguity"):
                return f"Encontrei mais de uma pessoa: {payload['assigneeAmbiguity']}. Pode informar o responsável completo?"
            return "\n".join(
                [
                    "Confirma a criação da atividade?",
                    "",
                    f"Título: {payload.get('title')}",
                    f"Responsável: {payload.get('assigneeName') or 'Sem responsável'}",
                    f"Prazo: {payload.get('dueDate') or 'Sem prazo'}",
                    f"Prioridade: {payload.get('priority')}",
                    f"Status: {payload.get('status')}",
                ]
            )
        if action_type == "update_activity":
            fields = payload.get("fields") or {}
            return "\n".join(
                [
                    "Confirma a atualização da atividade?",
                    "",
                    f"Atividade: {payload.get('activityTitle')}",
                    f"Campos: {fields}",
                ]
            )
        if action_type == "move_activity":
            lines = [
                "Confirma mover a atividade?",
                "",
                f"Atividade: {payload.get('activityTitle')}",
                f"Novo status: {payload.get('status')}",
            ]
            if payload.get("reason"):
                lines.append(f"Motivo: {payload.get('reason')}")
            return "\n".join(lines)
        if action_type == "add_comment":
            return "\n".join(
                [
                    "Confirma adicionar o comentário?",
                    "",
                    f"Atividade: {payload.get('activityTitle')}",
                    f"Comentário: {payload.get('message')}",
                ]
            )
        return "Confirma executar esta ação?"

    def _extract_priority(self, input_text: str) -> str | None:
        lowered = input_text.lower()
        if "crítica" in lowered or "critica" in lowered:
            return "CRITICAL"
        if "alta" in lowered:
            return "HIGH"
        if "baixa" in lowered:
            return "LOW"
        if "média" in lowered or "media" in lowered:
            return "MEDIUM"
        return None

    def _extract_due_date(self, input_text: str) -> str | None:
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", input_text)
        if match:
            return match.group(1)

        lowered = input_text.lower()
        if "amanhã" in lowered or "amanha" in lowered:
            return (date.today() + timedelta(days=1)).isoformat()

        weekdays = {
            "segunda": 0,
            "terça": 1,
            "terca": 1,
            "quarta": 2,
            "quinta": 3,
            "sexta": 4,
            "sábado": 5,
            "sabado": 5,
            "domingo": 6,
        }
        for name, weekday in weekdays.items():
            if name in lowered:
                today = date.today()
                delta = (weekday - today.weekday()) % 7
                if delta == 0:
                    delta = 7
                return (today + timedelta(days=delta)).isoformat()
        return None

    def _extract_create_title(self, input_text: str, assignee_name: str | None) -> str:
        title = re.sub(r"^\s*(cria|criar)\s+(uma\s+)?(nova\s+)?atividade\s*", "", input_text, flags=re.IGNORECASE)
        if assignee_name:
            first_name = re.escape(assignee_name.split(" ")[0])
            title = re.sub(rf"\bpara\s+{first_name}\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\bat[eé]\s+.+$", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\bcom prioridade\s+.+$", "", title, flags=re.IGNORECASE)
        return title.strip(" .,:;")[:120]

    def _clean_board_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        ignored = {"assigneeName", "assigneeAmbiguity", "activityTitle"}
        return {key: value for key, value in payload.items() if key not in ignored and value is not None}

    def _activity_title(self, activity: dict) -> str:
        return str(activity.get("title") or activity.get("name") or activity.get("id") or "Atividade")

    def _assignee_name(self, activity: dict) -> str:
        assignee = activity.get("assignee") or {}
        if isinstance(assignee, dict):
            return str(assignee.get("name") or "sem responsável")
        return str(activity.get("assigneeName") or "sem responsável")

    def _ambiguous_activity_message(self, activities: list[dict]) -> str:
        options = ", ".join(self._activity_title(activity) for activity in activities[:5])
        return f"Encontrei mais de uma atividade possível: {options}. Pode ser mais específico?"

    def _set_provider_context(self, conversation_id: str | None, message_id: str | None = None) -> None:
        setter = getattr(self.board_provider, "set_audit_context", None)
        if setter:
            setter(conversation_id, message_id)
