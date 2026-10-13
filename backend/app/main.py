from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    articles,
    assets,
    assistant,
    audit,
    auth,
    dashboard,
    health,
    ticket_assets,
    tickets,
    users,
)
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(users.router)
api.include_router(tickets.router)
api.include_router(assistant.router)
api.include_router(ticket_assets.router)
api.include_router(assets.router)
api.include_router(articles.router)
api.include_router(audit.router)
api.include_router(dashboard.router)
app.include_router(api)
