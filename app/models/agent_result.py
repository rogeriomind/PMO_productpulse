from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.board_action import BoardAction


AgentIntent = Literal[
    "create_task",
    "update_task",
    "change_due_date",
    "move_activity",
    "add_comment",
    "query_tasks",
    "query_alerts",
    "unknown",
]


class AgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: AgentIntent
    confidence: float = Field(ge=0, le=1)
    requires_confirmation: bool
    response_text: str
    board_action: BoardAction
    missing_fields: list[str] = Field(default_factory=list)
