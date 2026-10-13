import json
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import Select, func, select

from app.api.deps import SessionDep, require_roles
from app.models.audit import AuditLog
from app.models.user import Role, User
from app.schemas.audit import AuditFacets, AuditLogPage, AuditLogRead
from app.services.csv_export import to_csv

router = APIRouter(prefix="/audit-logs", tags=["audit"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]

AuditSelect = Select[Any]

# One export is capped so a single request cannot pull the whole table into memory.
EXPORT_LIMIT = 10_000


class Filters:
    """The filters shared by the list and the export, read from the query string."""

    def __init__(
        self,
        entity_type: str | None = None,
        entity_id: int | None = None,
        actor_id: int | None = None,
        action: str | None = None,
        from_date: Annotated[date | None, Query(alias="from")] = None,
        to_date: Annotated[date | None, Query(alias="to")] = None,
    ) -> None:
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.actor_id = actor_id
        self.action = action
        self.from_date = from_date
        self.to_date = to_date

    def apply(self, stmt: AuditSelect) -> AuditSelect:
        if self.entity_type:
            stmt = stmt.where(AuditLog.entity_type == self.entity_type)
        if self.entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == self.entity_id)
        if self.actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == self.actor_id)
        if self.action:
            stmt = stmt.where(AuditLog.action == self.action)
        # Dates are whole days in UTC, and "to" includes that day.
        if self.from_date:
            stmt = stmt.where(
                AuditLog.created_at >= datetime.combine(self.from_date, time.min, UTC)
            )
        if self.to_date:
            end = datetime.combine(self.to_date + timedelta(days=1), time.min, UTC)
            stmt = stmt.where(AuditLog.created_at < end)
        return stmt


FilterDep = Annotated[Filters, Depends()]


def _newest_first(stmt: AuditSelect) -> AuditSelect:
    return stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())


@router.get("")
async def list_audit_logs(
    session: SessionDep,
    _: AdminUser,
    filters: FilterDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditLogPage:
    stmt = filters.apply(select(AuditLog))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(_newest_first(stmt).limit(limit).offset(offset))
    return AuditLogPage(items=[AuditLogRead.model_validate(r) for r in rows], total=total)


@router.get("/facets")
async def audit_facets(session: SessionDep, _: AdminUser) -> AuditFacets:
    entity_types = await session.scalars(
        select(AuditLog.entity_type).distinct().order_by(AuditLog.entity_type)
    )
    actions = await session.scalars(select(AuditLog.action).distinct().order_by(AuditLog.action))
    return AuditFacets(entity_types=list(entity_types), actions=list(actions))


@router.get("/export.csv")
async def export_audit_logs(session: SessionDep, _: AdminUser, filters: FilterDep) -> Response:
    rows = await session.scalars(_newest_first(filters.apply(select(AuditLog))).limit(EXPORT_LIMIT))
    body = to_csv(
        ["id", "time_utc", "actor_id", "actor", "record_type", "record_id", "action", "changes"],
        (
            [
                r.id,
                r.created_at.astimezone(UTC).isoformat(),
                r.actor_id,
                r.actor.full_name if r.actor else "System",
                r.entity_type,
                r.entity_id,
                r.action,
                json.dumps(r.changes, sort_keys=True, ensure_ascii=False),
            ]
            for r in rows
        ),
    )
    filename = f"audit-log-{datetime.now(UTC).date().isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
