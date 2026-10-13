from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import SessionDep, require_roles
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.schemas.audit import AuditLogPage, AuditLogRead

router = APIRouter(prefix="/audit-logs", tags=["audit"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]


@router.get("")
async def list_audit_logs(
    session: SessionDep,
    _: AdminUser,
    entity_type: str | None = None,
    entity_id: int | None = None,
    actor_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    stmt = select(AuditLog)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.actor_id == actor_id)

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).offset(offset)
    )
    return AuditLogPage(items=[AuditLogRead.model_validate(r) for r in rows], total=total)
