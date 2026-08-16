from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConversationDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider: str
    provider_chat_id: str
    provider_user_id: str | None = None
    provider_user_name: str | None = None
    provider_username: str | None = None
    last_delivered_ui_context_id: str | None = None
    created_at: datetime
    updated_at: datetime


class MessageDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    conversation_id: str
    provider: str
    provider_message_id: str | None = None
    provider_update_id: str | None = None
    event_id: str | None = None
    direction: str
    message_type: str
    content_type: str
    raw_payload: dict[str, Any] | None = None
    normalized_text: str | None = None
    callback_query_id: str | None = None
    callback_data: str | None = None
    media_file_id: str | None = None
    media_url: str | None = None
    created_at: datetime


class AgentDispatchDTO(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    conversation_id: str
    request_id: str
    correlation_id: str
    thread_id: str
    source_message_ids: list[str] | None = None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None = None
    status: str
    attempts: int
    last_error: str | None = None
    agent_called_at: datetime | None = None
    delivered_at: datetime | None = None
    superseded_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ConversationDebugDTO(BaseModel):
    conversation: ConversationDTO
    messages: list[MessageDTO]
    dispatches: list[AgentDispatchDTO]
