from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ContentType = Literal["text", "audio", "image", "unknown"]
ProviderName = Literal["telegram", "whatsapp"]


class NormalizedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    provider_chat_id: str
    provider_user_id: str | None = None
    provider_user_name: str | None = None
    provider_username: str | None = None
    provider_message_id: str | None = None
    provider_update_id: str | None = None
    event_id: str
    content_type: ContentType
    text: str | None = None
    callback_query_id: str | None = None
    callback_data: str | None = None
    media_file_id: str | None = None
    media_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)

    @property
    def message_type(self) -> str:
        return self.content_type
