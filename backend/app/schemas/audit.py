from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.ticket import UserBrief


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: UserBrief | None
    entity_type: str
    entity_id: int
    action: str
    changes: dict[str, Any]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogRead]
    total: int


class AuditFacets(BaseModel):
    """The values that exist in the log, for building filter dropdowns."""

    entity_types: list[str]
    actions: list[str]
