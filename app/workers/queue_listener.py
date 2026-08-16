import logging
import random
import time
from typing import Any

from app.config import Settings
from app.database.connection import normalize_database_url

logger = logging.getLogger(__name__)


class QueueListener:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.connection: Any | None = None
        self.reconnect_delay_seconds = 1.0

    def wait(self, timeout_seconds: float) -> bool:
        try:
            self._ensure_connected()
            for notify in self.connection.notifies(
                timeout=timeout_seconds, stop_after=1
            ):
                received = (
                    notify.channel == self.settings.effective_queue_notify_channel
                )
                logger.info(
                    "queue_notification_received",
                    extra={
                        "payload": {
                            "channel": notify.channel,
                            "payload": notify.payload,
                            "received": received,
                        }
                    },
                )
                return received
            logger.info(
                "worker_idle",
                extra={"payload": {"timeout_seconds": timeout_seconds}},
            )
            return False
        except Exception as exc:
            self.close()
            logger.warning(
                "queue_notification_error",
                extra={"payload": {"error": str(exc)}},
            )
            self._sleep_before_reconnect(timeout_seconds)
            return True

    def close(self) -> None:
        if self.connection is None:
            return
        try:
            self.connection.close()
        finally:
            self.connection = None

    def _ensure_connected(self) -> None:
        if self.connection is not None:
            return

        import psycopg
        from psycopg import sql

        database_url = normalize_database_url(self.settings.database_url).replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        connection = psycopg.connect(database_url, autocommit=True)
        channel = self.settings.effective_queue_notify_channel
        connection.execute(sql.SQL("LISTEN {}").format(sql.Identifier(channel)))
        self.connection = connection
        self.reconnect_delay_seconds = 1.0
        logger.info(
            "worker_notify_listening",
            extra={
                "payload": {
                    "channel": channel,
                    "fallback_poll_seconds": (
                        self.settings.effective_worker_fallback_poll_seconds
                    ),
                }
            },
        )

    def _sleep_before_reconnect(self, timeout_seconds: float) -> None:
        delay = min(
            self.reconnect_delay_seconds,
            self.settings.queue_notify_reconnect_max_seconds,
            timeout_seconds,
        )
        if delay > 0:
            time.sleep(delay + random.uniform(0, delay * 0.1))
        self.reconnect_delay_seconds = min(
            self.reconnect_delay_seconds * 2,
            self.settings.queue_notify_reconnect_max_seconds,
        )
        logger.info(
            "queue_notification_reconnect",
            extra={"payload": {"next_delay_seconds": self.reconnect_delay_seconds}},
        )
