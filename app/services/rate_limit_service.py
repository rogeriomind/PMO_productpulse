from datetime import timedelta

from app.database.connection import utcnow
from app.repositories.message_repository import MessageRepository
from app.services.audit_service import AuditService


class RateLimitService:
    def __init__(
        self,
        message_repository: MessageRepository,
        audit_service: AuditService,
        max_messages: int,
        window_seconds: int,
    ):
        self.message_repository = message_repository
        self.audit_service = audit_service
        self.max_messages = max_messages
        self.window_seconds = window_seconds

    def is_allowed(self, conversation_id: str) -> bool:
        since = utcnow() - timedelta(seconds=self.window_seconds)
        recent_count = self.message_repository.count_recent_inbound(conversation_id, since)
        allowed = recent_count < self.max_messages
        if not allowed:
            self.audit_service.record(
                "rate_limited",
                "blocked",
                conversation_id=conversation_id,
                payload={"recent_count": recent_count, "window_seconds": self.window_seconds},
            )
        return allowed
