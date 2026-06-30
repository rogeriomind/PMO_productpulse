from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


MessageType = Literal["text", "audio", "image", "unknown"]
ProviderName = Literal["telegram", "whatsapp"]


class NormalizedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: ProviderName
    provider_chat_id: str
    provider_user_id: str | None = None
    provider_message_id: str | None = None
    message_type: MessageType
    text: str | None = None
    media_file_id: str | None = None
    media_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
