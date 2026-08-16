import logging
from types import TracebackType

import httpx
from sqlalchemy.orm import Session

from app.clients.agent_api_client import AgentApiClient
from app.config import Settings
from app.integrations.agent_event_mapper import AgentEventMapper
from app.providers.mock_transcription_provider import MockTranscriptionProvider
from app.providers.telegram_provider import TelegramMessageProvider
from app.providers.whatsapp_provider_mock import WhatsAppMessageProviderMock
from app.renderers.channel_response_renderer import ChannelResponseRenderer

logger = logging.getLogger(__name__)


class WorkerRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.agent_http_client = httpx.Client(
            timeout=httpx.Timeout(
                connect=5.0,
                read=settings.agent_api_timeout_seconds,
                write=10.0,
                pool=5.0,
            ),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10,
                keepalive_expiry=30.0,
            ),
        )
        self.agent_api_client = AgentApiClient(
            settings=settings, client=self.agent_http_client
        )
        self.agent_event_mapper = AgentEventMapper(settings)
        self.response_renderer = ChannelResponseRenderer()
        self.telegram_http_client = httpx.Client(timeout=10.0)
        self.telegram_provider = TelegramMessageProvider(
            settings, client=self.telegram_http_client
        )
        self.whatsapp_provider = WhatsAppMessageProviderMock()
        self.transcription_provider = MockTranscriptionProvider()

        logger.info(
            "worker_runtime_started",
            extra={
                "payload": {
                    "queue_notify_enabled": settings.queue_notify_active,
                    "queue_notify_channel": settings.effective_queue_notify_channel,
                    "worker_max_drain_batch": settings.worker_max_drain_batch,
                }
            },
        )

    def create_worker(self, db: Session):
        from app.workers.message_worker import MessageWorker

        return MessageWorker(
            db=db,
            settings=self.settings,
            agent_api_client=self.agent_api_client,
            agent_event_mapper=self.agent_event_mapper,
            response_renderer=self.response_renderer,
            telegram_provider=self.telegram_provider,
            whatsapp_provider=self.whatsapp_provider,
            transcription_provider=self.transcription_provider,
        )

    def close(self) -> None:
        self.agent_api_client.close()
        self.telegram_http_client.close()
        logger.info("worker_runtime_stopped", extra={"payload": {}})

    def __enter__(self) -> "WorkerRuntime":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
