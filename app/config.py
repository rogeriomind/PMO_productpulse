from functools import lru_cache

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

    debounce_seconds: int = Field(default=5, alias="DEBOUNCE_SECONDS")

    max_queue_attempts: int = Field(default=3, alias="MAX_QUEUE_ATTEMPTS")
    queue_lock_seconds: int = Field(default=60, alias="QUEUE_LOCK_SECONDS")
    worker_sleep_seconds: int = Field(default=2, alias="WORKER_SLEEP_SECONDS")

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
        if self.app_env.lower() in {"prod", "production"}:
            if (
                "agent_api_url" not in self.model_fields_set
                or not self.agent_api_url.strip()
            ):
                raise ValueError("AGENT_API_URL é obrigatório em produção")
            if not self.agent_api_token.get_secret_value().strip():
                raise ValueError("AGENT_API_TOKEN é obrigatório em produção")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
