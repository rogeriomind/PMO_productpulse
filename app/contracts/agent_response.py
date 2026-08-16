from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentStatus = Literal[
    "completed",
    "waiting_user_input",
    "awaiting_confirmation",
    "cancelled",
    "not_found",
    "validation_error",
    "unauthorized",
    "conflict",
    "degraded",
    "error",
]
AgentUiType = Literal["none", "inline_keyboard", "numbered_list", "confirmation"]


class AgentUiOption(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    callback_data: str | None = None
    row: int | None = None


class AgentUi(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: AgentUiType = "none"
    options: list[AgentUiOption] = Field(default_factory=list)
    context_id: str | None = None


class AgentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    request_id: str
    correlation_id: str
    thread_id: str
    status: AgentStatus
    flow: str | None = None
    step: str | None = None
    message: str
    ui: AgentUi = Field(default_factory=AgentUi)
    data: dict[str, Any] = Field(default_factory=dict)
    requires_confirmation: bool = False
    confirmation: dict[str, Any] | None = None
    error: dict[str, Any] | str | None = None
