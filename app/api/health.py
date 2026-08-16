from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database.connection import get_db

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/ready")
def ready(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> dict:
    checks: dict[str, str] = {}
    status = "ok"

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "failed"
        status = "degraded"

    try:
        db.execute(text("SELECT 1 FROM message_queue LIMIT 1"))
        checks["queue"] = "ok"
    except Exception:
        checks["queue"] = "failed"
        status = "degraded"

    token_configured = bool(settings.agent_api_token.get_secret_value().strip())
    if settings.agent_api_url.strip() and (
        settings.app_env.lower() not in {"prod", "production"} or token_configured
    ):
        checks["agent_api"] = "ok"
    else:
        checks["agent_api"] = "degraded"
        status = "degraded"

    return {"status": status, "checks": checks}
