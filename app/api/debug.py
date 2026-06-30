from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.connection import get_db
from app.models.conversation import ConversationDTO, ConversationDebugDTO, MessageDTO, TaskActionDTO
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.task_action_repository import TaskActionRepository
from app.workers.message_worker import MessageWorker

router = APIRouter(tags=["debug"])


@router.get("/debug/conversations/{conversation_id}", response_model=ConversationDebugDTO)
def debug_conversation(conversation_id: str, db: Session = Depends(get_db)) -> ConversationDebugDTO:
    conversation = ConversationRepository(db).get(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    messages = MessageRepository(db).list_by_conversation(conversation_id)
    actions = TaskActionRepository(db).list_by_conversation(conversation_id)
    return ConversationDebugDTO(
        conversation=ConversationDTO.model_validate(conversation),
        messages=[MessageDTO.model_validate(message) for message in messages],
        actions=[TaskActionDTO.model_validate(action) for action in actions],
    )


@router.get("/debug/actions/{action_id}", response_model=TaskActionDTO)
def debug_action(action_id: str, db: Session = Depends(get_db)) -> TaskActionDTO:
    action = TaskActionRepository(db).get(action_id)
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    return TaskActionDTO.model_validate(action)


@router.post("/workers/process-message")
def process_message_once(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    worker = MessageWorker(db, settings)
    return worker.process_once()
