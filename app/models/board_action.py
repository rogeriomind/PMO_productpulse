from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


BoardActionType = Literal[
    "create_activity",
    "update_activity",
    "move_activity",
    "add_comment",
    "query_activities",
    "query_alerts",
    "unknown",
]


class BoardAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: BoardActionType
    payload: dict[str, Any] = Field(default_factory=dict)
