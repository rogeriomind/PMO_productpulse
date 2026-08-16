from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = Field(default="local", alias="APP_ENV")
    app_port: int = Field(default=8000, alias="APP_PORT")

    database_url: str = Field(
        default="postgresql://pmo_agent:pmo_agent@postgres:5432/pmo_agent",
        alias="DATABASE_URL",
    )

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_webhook_secret: str = Field(default="", alias="TELEGRAM_WEBHOOK_SECRET")

    debounce_seconds: float = Field(default=1.0, alias="DEBOUNCE_SECONDS")
    debounce_max_seconds: float = Field(default=2.0, alias="DEBOUNCE_MAX_SECONDS")
    debounce_adaptive_enabled: bool = Field(
        default=False, alias="DEBOUNCE_ADAPTIVE_ENABLED"
    )
    debounce_min_ms: int = Field(default=700, alias="DEBOUNCE_MIN_MS")
    debounce_max_ms: int = Field(default=2500, alias="DEBOUNCE_MAX_MS")
    debounce_increment_ms: int = Field(default=400, alias="DEBOUNCE_INCREMENT_MS")
    debounce_max_messages: int = Field(default=8, alias="DEBOUNCE_MAX_MESSAGES")

    max_queue_attempts: int = Field(default=3, alias="MAX_QUEUE_ATTEMPTS")
    queue_lock_seconds: int = Field(default=60, alias="QUEUE_LOCK_SECONDS")
    worker_sleep_seconds: float = Field(default=0.2, alias="WORKER_SLEEP_SECONDS")
    worker_backoff_max_seconds: float = Field(
        default=1.0, alias="WORKER_BACKOFF_MAX_SECONDS"
    )
    worker_wakeup_mode: Literal["polling", "postgres_notify"] = Field(
        default="polling", alias="WORKER_WAKEUP_MODE"
    )
    worker_notify_channel: str = Field(default="", alias="WORKER_NOTIFY_CHANNEL")
    worker_notify_safety_poll_seconds: float = Field(
        default=5.0, alias="WORKER_NOTIFY_SAFETY_POLL_SECONDS"
    )
    worker_fallback_poll_seconds: float = Field(
        default=10.0, alias="WORKER_FALLBACK_POLL_SECONDS"
    )
    worker_max_drain_batch: int = Field(default=100, alias="WORKER_MAX_DRAIN_BATCH")

    queue_notify_enabled: bool = Field(default=False, alias="QUEUE_NOTIFY_ENABLED")
    queue_notify_channel: str = Field(
        default="pmo_productpulse_queue", alias="QUEUE_NOTIFY_CHANNEL"
    )
    queue_notify_reconnect_max_seconds: float = Field(
        default=15.0, alias="QUEUE_NOTIFY_RECONNECT_MAX_SECONDS"
    )

    rate_limit_max_messages: int = Field(default=20, alias="RATE_LIMIT_MAX_MESSAGES")
    rate_limit_window_seconds: int = Field(
        default=60, alias="RATE_LIMIT_WINDOW_SECONDS"
    )

    agent_api_url: str = Field(
        default="http://pmo-ai-agent-api:8010", alias="AGENT_API_URL"
    )
    agent_api_token: SecretStr = Field(default=SecretStr(""), alias="AGENT_API_TOKEN")
    agent_api_timeout_seconds: int = Field(
        default=30, alias="AGENT_API_TIMEOUT_SECONDS"
    )
    agent_api_retry_attempts: int = Field(default=3, alias="AGENT_API_RETRY_ATTEMPTS")
    agent_api_retry_base_seconds: float = Field(
        default=1, alias="AGENT_API_RETRY_BASE_SECONDS"
    )
    agent_api_endpoint: str = Field(
        default="/v2/agent/events", alias="AGENT_API_ENDPOINT"
    )

    agent_tenant_id: str = Field(default="default", alias="AGENT_TENANT_ID")
    agent_default_project_id: str | None = Field(
        default=None, alias="AGENT_DEFAULT_PROJECT_ID"
    )
    agent_timezone: str = Field(default="America/Sao_Paulo", alias="AGENT_TIMEZONE")
    agent_technical_fallback_message: str = Field(
        default="O serviço está temporariamente indisponível. Tente novamente em alguns instantes.",
        alias="AGENT_TECHNICAL_FALLBACK_MESSAGE",
    )

    @model_validator(mode="after")
    def validate_production_agent_config(self) -> "Settings":
        if self.debounce_seconds < 0:
            raise ValueError("DEBOUNCE_SECONDS não pode ser negativo")
        if self.debounce_max_seconds < self.debounce_seconds:
            raise ValueError("DEBOUNCE_MAX_SECONDS deve ser >= DEBOUNCE_SECONDS")
        if self.debounce_min_ms < 0:
            raise ValueError("DEBOUNCE_MIN_MS não pode ser negativo")
        if self.debounce_max_ms < self.debounce_min_ms:
            raise ValueError("DEBOUNCE_MAX_MS deve ser >= DEBOUNCE_MIN_MS")
        if self.debounce_increment_ms < 0:
            raise ValueError("DEBOUNCE_INCREMENT_MS não pode ser negativo")
        if self.debounce_max_messages <= 0:
            raise ValueError("DEBOUNCE_MAX_MESSAGES deve ser maior que zero")
        if self.worker_sleep_seconds <= 0:
            raise ValueError("WORKER_SLEEP_SECONDS deve ser maior que zero")
        if self.worker_backoff_max_seconds < self.worker_sleep_seconds:
            raise ValueError(
                "WORKER_BACKOFF_MAX_SECONDS deve ser >= WORKER_SLEEP_SECONDS"
            )
        if self.worker_notify_safety_poll_seconds <= 0:
            raise ValueError(
                "WORKER_NOTIFY_SAFETY_POLL_SECONDS deve ser maior que zero"
            )
        if self.worker_fallback_poll_seconds <= 0:
            raise ValueError("WORKER_FALLBACK_POLL_SECONDS deve ser maior que zero")
        if self.worker_max_drain_batch <= 0:
            raise ValueError("WORKER_MAX_DRAIN_BATCH deve ser maior que zero")
        if not self.effective_queue_notify_channel.strip():
            raise ValueError("QUEUE_NOTIFY_CHANNEL não pode ser vazio")
        if self.queue_notify_reconnect_max_seconds <= 0:
            raise ValueError(
                "QUEUE_NOTIFY_RECONNECT_MAX_SECONDS deve ser maior que zero"
            )
        if self.app_env.lower() in {"prod", "production"}:
            if (
                "agent_api_url" not in self.model_fields_set
                or not self.agent_api_url.strip()
            ):
                raise ValueError("AGENT_API_URL é obrigatório em produção")
            if not self.agent_api_token.get_secret_value().strip():
                raise ValueError("AGENT_API_TOKEN é obrigatório em produção")
        return self

    @property
    def effective_queue_notify_channel(self) -> str:
        return self.worker_notify_channel or self.queue_notify_channel

    @property
    def queue_notify_active(self) -> bool:
        return self.queue_notify_enabled or self.worker_wakeup_mode == "postgres_notify"

    @property
    def effective_worker_fallback_poll_seconds(self) -> float:
        if self.worker_notify_safety_poll_seconds != 5.0:
            return self.worker_notify_safety_poll_seconds
        return self.worker_fallback_poll_seconds


@lru_cache
def get_settings() -> Settings:
    return Settings()
