import logging

from app.repositories.audit_repository import AuditRepository

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, repository: AuditRepository):
        self.repository = repository

    def record(
        self,
        event_type: str,
        status: str = "success",
        conversation_id: str | None = None,
        message_id: str | None = None,
        payload: dict | None = None,
        error_message: str | None = None,
    ) -> None:
        logger.info(
            event_type,
            extra={
                "payload": {
                    "event_type": event_type,
                    "status": status,
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "payload": payload or {},
                    "error_message": error_message,
                }
            },
        )
        self.repository.create(
            event_type=event_type,
            status=status,
            conversation_id=conversation_id,
            message_id=message_id,
            payload=payload,
            error_message=error_message,
        )
