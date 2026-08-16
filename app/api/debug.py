from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.connection import get_db
from app.models.conversation import (
    AgentDispatchDTO,
    ConversationDTO,
    ConversationDebugDTO,
    MessageDTO,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.agent_dispatch_repository import AgentDispatchRepository
from app.repositories.message_repository import MessageRepository
from app.workers.message_worker import MessageWorker

router = APIRouter(tags=["debug"])


@router.get(
    "/debug/conversations/{conversation_id}", response_model=ConversationDebugDTO
)
def debug_conversation(
    conversation_id: str, db: Session = Depends(get_db)
) -> ConversationDebugDTO:
    conversation = ConversationRepository(db).get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = MessageRepository(db).list_by_conversation(conversation_id)
    dispatches = AgentDispatchRepository(db).list_by_conversation(conversation_id)
    return ConversationDebugDTO(
        conversation=ConversationDTO.model_validate(conversation),
        messages=[MessageDTO.model_validate(message) for message in messages],
        dispatches=[
            AgentDispatchDTO.model_validate(dispatch) for dispatch in dispatches
        ],
    )


@router.post("/workers/process-message")
def process_message_once(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    worker = MessageWorker(db, settings)
    return worker.process_once()
