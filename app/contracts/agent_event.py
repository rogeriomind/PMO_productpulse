from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentEventType = Literal[
    "welcome",
    "text",
    "menu_selection",
    "task_selection",
    "confirmation",
    "cancel",
    "back",
    "reset",
]


class AgentEventUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    name: str | None = None
    username: str | None = None


class AgentEventContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str | None = None
    callback_data: str | None = None


class AgentEventMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chat_id: str
    message_id: str | None = None
    provider_update_id: str | None = None
    project_id: str | None = None
    timezone: str
    content_type: str
    source_message_ids: list[str] = Field(default_factory=list)
    callback_query_id: str | None = None
    transcribed: bool | None = None


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    request_id: str
    correlation_id: str
    thread_id: str
    tenant_id: str
    channel: Literal["telegram", "whatsapp"]
    message_type: AgentEventType
    user: AgentEventUser
    content: AgentEventContent
    metadata: AgentEventMetadata

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
