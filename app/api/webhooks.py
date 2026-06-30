from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.connection import get_db
from app.services.inbound_service import InboundService

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/telegram", status_code=status.HTTP_202_ACCEPTED)
def telegram_webhook(
    payload: dict,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    if settings.telegram_webhook_secret and x_telegram_bot_api_secret_token != settings.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Telegram webhook secret")
    return InboundService(db, settings).receive("telegram", payload)


@router.post("/whatsapp", status_code=status.HTTP_202_ACCEPTED)
def whatsapp_webhook(
    payload: dict,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return InboundService(db, settings).receive("whatsapp", payload)
