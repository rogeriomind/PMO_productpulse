from functools import lru_cache

from pydantic import Field
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
    rate_limit_window_seconds: int = Field(default=60, alias="RATE_LIMIT_WINDOW_SECONDS")

    pmo_api_url: str = Field(default="http://localhost:3333/api", alias="PMO_API_URL")
    pmo_api_email: str = Field(default="rogerio@pmo.local", alias="PMO_API_EMAIL")
    pmo_api_password: str = Field(default="123456", alias="PMO_API_PASSWORD")
    pmo_api_timeout_seconds: int = Field(default=10, alias="PMO_API_TIMEOUT_SECONDS")
    pmo_api_retry_attempts: int = Field(default=2, alias="PMO_API_RETRY_ATTEMPTS")

    board_provider: str = Field(default="pmo_board", alias="BOARD_PROVIDER")


@lru_cache
def get_settings() -> Settings:
    return Settings()
