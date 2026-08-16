from app.contracts.agent_event import AgentEvent
from app.contracts.agent_response import AgentResponse
from app.database.connection import AgentDispatchRecord
from app.repositories.agent_dispatch_repository import AgentDispatchRepository
from app.services.audit_service import AuditService


class AgentDispatchService:
    def __init__(
        self, repository: AgentDispatchRepository, audit_service: AuditService
    ):
        self.repository = repository
        self.audit_service = audit_service

    def get_or_create(
        self, conversation_id: str, event: AgentEvent
    ) -> AgentDispatchRecord:
        dispatch = self.repository.get_by_event_id(event.event_id)
        if dispatch:
            if dispatch.response_payload:
                self.audit_service.record(
                    "agent_api_response_replayed",
                    "success",
                    conversation_id=conversation_id,
                    payload=self._audit_payload(dispatch),
                )
            return dispatch
        return self.repository.create(
            event_id=event.event_id,
            conversation_id=conversation_id,
            request_id=event.request_id,
            correlation_id=event.correlation_id,
            thread_id=event.thread_id,
            source_message_ids=event.metadata.source_message_ids,
            request_payload=event.to_payload(),
        )

    def mark_calling(self, dispatch_id: str) -> None:
        self.repository.mark_calling(dispatch_id)

    def save_response(
        self, dispatch: AgentDispatchRecord, response: AgentResponse
    ) -> AgentDispatchRecord:
        saved = self.repository.save_response(
            dispatch.id, response.model_dump(mode="json")
        )
        dispatch = saved or dispatch
        self.audit_service.record(
            "agent_response_persisted",
            "success",
            conversation_id=dispatch.conversation_id,
            payload=self._audit_payload(dispatch),
        )
        return dispatch

    def mark_delivering(self, dispatch_id: str) -> None:
        self.repository.mark_delivering(dispatch_id)

    def mark_delivered(self, dispatch_id: str) -> None:
        self.repository.mark_delivered(dispatch_id)

    def mark_superseded(self, dispatch_id: str) -> None:
        dispatch = self.repository.mark_superseded(dispatch_id)
        if dispatch:
            self.audit_service.record(
                "agent_delivery_suppressed",
                "superseded",
                conversation_id=dispatch.conversation_id,
                payload=self._audit_payload(dispatch),
            )

    def mark_retry(self, dispatch_id: str, error_message: str) -> None:
        self.repository.mark_retry(dispatch_id, error_message)

    def mark_failed(self, dispatch_id: str, error_message: str) -> None:
        self.repository.mark_failed(dispatch_id, error_message)

    def mark_delivery_failed(self, dispatch_id: str, error_message: str) -> None:
        self.repository.mark_delivery_failed(dispatch_id, error_message)

    def _audit_payload(self, dispatch: AgentDispatchRecord) -> dict:
        return {
            "event_id": dispatch.event_id,
            "request_id": dispatch.request_id,
            "correlation_id": dispatch.correlation_id,
            "thread_id": dispatch.thread_id,
            "dispatch_id": dispatch.id,
            "status": dispatch.status,
            "attempts": dispatch.attempts,
        }
