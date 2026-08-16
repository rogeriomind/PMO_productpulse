from fastapi import FastAPI

from app.api import debug, health, webhooks
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(title="PMO ProductPulse Channel Gateway", version="0.2.0")
app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(debug.router)
