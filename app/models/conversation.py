from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConversationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    provider_chat_id: str
    provider_user_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    provider: str
    provider_message_id: str | None = None
    direction: str
    message_type: str
    raw_payload: dict[str, Any] | None = None
    normalized_text: str | None = None
    media_file_id: str | None = None
    media_url: str | None = None
    created_at: datetime


class TaskActionDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    user_id: str | None = None
    intent: str
    action_payload: dict[str, Any]
    status: str
    confirmation_token: str | None = None
    confirmed_at: datetime | None = None
    executed_at: datetime | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDebugDTO(BaseModel):
    conversation: ConversationDTO
    messages: list[MessageDTO]
    actions: list[TaskActionDTO]
