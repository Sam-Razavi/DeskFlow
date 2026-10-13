from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, SessionDep
from app.models.asset import Asset, AssetStatus
from app.models.ticket import Priority, Ticket, TicketStatus
from app.models.user import Role
from app.schemas.asset import WARRANTY_WARNING_DAYS
from app.schemas.dashboard import DashboardSummary
from app.services import sla
from app.services.sla import SlaState

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def summary(session: SessionDep, user: CurrentUser) -> DashboardSummary:
    """Counts for the dashboard. Requesters only ever see figures for their own tickets."""
    stmt = select(
        Ticket.priority,
        Ticket.status,
        Ticket.assignee_id,
        Ticket.created_at,
        Ticket.resolved_at,
        Ticket.first_response_at,
        Ticket.response_due_at,
        Ticket.resolution_due_at,
        Ticket.sla_paused_at,
    ).where(Ticket.status != TicketStatus.CLOSED)
    if user.role == Role.REQUESTER:
        stmt = stmt.where(Ticket.requester_id == user.id)

    now = sla.utcnow()
    by_priority: Counter[Priority] = Counter()
    breached = at_risk = unassigned = mine = awaiting = 0
    for row in await session.execute(stmt):
        if row.status == TicketStatus.RESOLVED:
            awaiting += 1
            continue
        by_priority[row.priority] += 1
        if row.assignee_id is None:
            unassigned += 1
        elif row.assignee_id == user.id:
            mine += 1
        state = sla.overall_state(row, now)
        breached += state == SlaState.BREACHED
        at_risk += state == SlaState.AT_RISK

    in_repair = expiring = 0
    if user.role != Role.REQUESTER:
        in_repair = (
            await session.scalar(
                select(func.count()).select_from(Asset).where(Asset.status == AssetStatus.IN_REPAIR)
            )
        ) or 0
        today = datetime.now(UTC).date()
        expiring = (
            await session.scalar(
                select(func.count())
                .select_from(Asset)
                .where(
                    Asset.status != AssetStatus.RETIRED,
                    Asset.warranty_expires_on.between(
                        today, today + timedelta(days=WARRANTY_WARNING_DAYS)
                    ),
                )
            )
        ) or 0

    return DashboardSummary(
        open_total=sum(by_priority.values()),
        open_by_priority={p: by_priority[p] for p in Priority},
        sla_breached=breached,
        sla_at_risk=at_risk,
        unassigned=unassigned,
        assigned_to_me=mine,
        awaiting_confirmation=awaiting,
        assets_in_repair=in_repair,
        warranty_expiring=expiring,
    )
