from fastapi import FastAPI

from app.api import debug, health, webhooks
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(title="PMO Agent Message Pipeline MVP", version="0.1.0")
app.include_router(health.router)
app.include_router(webhooks.router)
app.include_router(debug.router)
