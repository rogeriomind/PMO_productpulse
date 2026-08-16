from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChannelOutboundMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    reply_markup: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
