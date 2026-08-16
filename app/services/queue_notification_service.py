import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings

logger = logging.getLogger(__name__)


class QueueNotificationService:
    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    def notify_new_item(self, queue_id: str) -> bool:
        if not self.settings.queue_notify_active:
            return False

        channel = self.settings.effective_queue_notify_channel
        bind = self.db.get_bind()
        if bind.dialect.name != "postgresql":
            return False

        try:
            self.db.execute(
                text("SELECT pg_notify(:channel, :payload)"),
                {"channel": channel, "payload": queue_id},
            )
            self.db.commit()
            logger.info(
                "queue_notification_sent",
                extra={"payload": {"queue_id": queue_id, "channel": channel}},
            )
            return True
        except Exception as exc:
            self.db.rollback()
            logger.warning(
                "queue_notification_error",
                extra={
                    "payload": {
                        "queue_id": queue_id,
                        "channel": channel,
                        "error": str(exc),
                    }
                },
            )
            return False
