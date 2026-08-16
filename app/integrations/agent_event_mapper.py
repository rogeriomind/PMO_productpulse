import hashlib
import uuid

from app.config import Settings
from app.contracts.agent_event import (
    AgentEvent,
    AgentEventContent,
    AgentEventMetadata,
    AgentEventUser,
    AgentEventType,
)
from app.database.connection import ConversationRecord, MessageRecord


class AgentEventMapper:
    def __init__(self, settings: Settings):
        self.settings = settings

    def map(
        self,
        conversation: ConversationRecord,
        message: MessageRecord,
        processed_text: str | None,
        *,
        event_id: str | None = None,
        source_message_ids: list[str] | None = None,
        content_type: str | None = None,
        transcribed: bool = False,
    ) -> AgentEvent:
        final_event_id = (
            event_id
            or message.event_id
            or self.debounce_event_id(
                conversation.provider,
                conversation.id,
                [message.id],
                processed_text or "",
            )
        )
        source_ids = source_message_ids or [message.id]
        agent_event_type = self._event_type(message, processed_text)
        thread_id = self.thread_id(conversation.provider, conversation.provider_chat_id)
        request_id = str(uuid.uuid5(uuid.NAMESPACE_URL, final_event_id))
        correlation_id = str(uuid.uuid4())

        return AgentEvent(
            event_id=final_event_id,
            request_id=request_id,
            correlation_id=correlation_id,
            thread_id=thread_id,
            tenant_id=self.settings.agent_tenant_id,
            channel=conversation.provider,
            message_type=agent_event_type,
            user=AgentEventUser(
                id=conversation.provider_user_id,
                name=conversation.provider_user_name,
                username=conversation.provider_username,
            ),
            content=AgentEventContent(
                text=processed_text if processed_text != "" else None,
                callback_data=message.callback_data,
            ),
            metadata=AgentEventMetadata(
                chat_id=conversation.provider_chat_id,
                message_id=message.provider_message_id,
                provider_update_id=message.provider_update_id,
                project_id=self.settings.agent_default_project_id,
                timezone=self.settings.agent_timezone,
                content_type=content_type
                or message.content_type
                or message.message_type,
                source_message_ids=source_ids,
                callback_query_id=message.callback_query_id,
                transcribed=True if transcribed else None,
                extra=_metadata_extra(conversation),
            ),
        )

    def thread_id(self, provider: str, provider_chat_id: str) -> str:
        return f"{self.settings.agent_tenant_id}:{provider}:{provider_chat_id}"

    def debounce_event_id(
        self,
        provider: str,
        conversation_id: str,
        source_message_ids: list[str],
        combined_text: str,
    ) -> str:
        material = "|".join(
            [provider, conversation_id, *sorted(source_message_ids), combined_text]
        )
        digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
        return f"{provider}:debounce:{digest}"

    def _event_type(
        self, message: MessageRecord, processed_text: str | None
    ) -> AgentEventType:
        callback_data = (message.callback_data or "").strip()
        if callback_data:
            if callback_data.startswith("menu:"):
                return "menu_selection"
            if callback_data.startswith(
                ("status:task:", "status:id:", "update:task:", "task:")
            ):
                return "task_selection"
            if callback_data.startswith("confirmation:"):
                return "confirmation"
            if callback_data == "global:cancel":
                return "cancel"
            if callback_data == "global:back":
                return "back"
            if callback_data == "global:reset":
                return "reset"
            return "text"

        text = (processed_text or message.normalized_text or "").strip()
        if text == "/start" or text.startswith("/start "):
            return "welcome"
        return "text"


def _metadata_extra(conversation: ConversationRecord) -> dict[str, str]:
    context_id = getattr(conversation, "last_delivered_ui_context_id", None)
    return {"ui_context_id": context_id} if context_id else {}
