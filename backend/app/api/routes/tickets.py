from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import STAFF_ROLES, is_staff, load_ticket
from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models.audit import AuditLog
from app.models.ticket import Category, Priority, Ticket, TicketComment, TicketStatus
from app.models.user import User
from app.schemas.audit import AuditLogRead
from app.schemas.ticket import (
    AssigneeChange,
    CommentCreate,
    CommentRead,
    StatusChange,
    TicketCreate,
    TicketPage,
    TicketRead,
    TicketUpdate,
)
from app.services import audit, sla
from app.services.workflow import can_transition

router = APIRouter(prefix="/tickets", tags=["tickets"])

StaffUser = Annotated[User, Depends(require_roles(*STAFF_ROLES))]

TRACKED_FIELDS = ("title", "description", "status", "priority", "category", "assignee_id")


def _snapshot(ticket: Ticket) -> dict[str, object]:
    return {f: getattr(ticket, f) for f in TRACKED_FIELDS}


async def _require_staff_user(session: AsyncSession, user_id: int, what: str) -> User:
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown {what}")
    return user


async def _ticket_ids_in_sla_state(
    session: AsyncSession, wanted: Literal["breached", "at_risk"]
) -> list[int]:
    """Ids of open, running tickets in the given state, judged by the same rules as the API.

    The state depends on the current time, so it is evaluated in Python over open tickets rather
    than re-implemented in SQL where the two could drift apart.
    """
    now = sla.utcnow()
    rows = await session.execute(
        select(
            Ticket.id,
            Ticket.status,
            Ticket.created_at,
            Ticket.resolved_at,
            Ticket.first_response_at,
            Ticket.response_due_at,
            Ticket.resolution_due_at,
            Ticket.sla_paused_at,
        ).where(Ticket.status.not_in(sla.DONE_STATUSES))
    )
    return [r.id for r in rows if sla.overall_state(r, now).value == wanted]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(session: SessionDep, user: CurrentUser, body: TicketCreate) -> TicketRead:
    requester_id = user.id
    if is_staff(user) and body.requester_id is not None:
        requester_id = (await _require_staff_user(session, body.requester_id, "requester")).id

    now = sla.utcnow()
    response_due, resolution_due = sla.due_dates(now, body.priority)
    ticket = Ticket(
        title=body.title,
        description=body.description,
        priority=body.priority,
        category=body.category,
        requester_id=requester_id,
        created_at=now,
        response_due_at=response_due,
        resolution_due_at=resolution_due,
    )
    session.add(ticket)
    await session.flush()
    audit.record(
        session,
        user,
        "ticket",
        ticket.id,
        "created",
        {**_snapshot(ticket), "status": TicketStatus.NEW, "requester_id": requester_id},
    )
    await session.commit()
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.get("")
async def list_tickets(
    session: SessionDep,
    user: CurrentUser,
    status_: Annotated[TicketStatus | None, Query(alias="status")] = None,
    priority: Priority | None = None,
    category: Category | None = None,
    assignee_id: int | None = None,
    unassigned: bool = False,
    sla_filter: Annotated[Literal["breached", "at_risk"] | None, Query(alias="sla")] = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketPage:
    stmt = select(Ticket)
    if not is_staff(user):
        stmt = stmt.where(Ticket.requester_id == user.id)
    if status_:
        stmt = stmt.where(Ticket.status == status_)
    if priority:
        stmt = stmt.where(Ticket.priority == priority)
    if category:
        stmt = stmt.where(Ticket.category == category)
    if unassigned:
        stmt = stmt.where(Ticket.assignee_id.is_(None))
    elif assignee_id is not None:
        stmt = stmt.where(Ticket.assignee_id == assignee_id)
    if sla_filter:
        stmt = stmt.where(Ticket.id.in_(await _ticket_ids_in_sla_state(session, sla_filter)))
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(or_(Ticket.title.ilike(pattern), Ticket.description.ilike(pattern)))

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    # Most urgent first, then oldest first within a priority.
    rows = await session.scalars(
        stmt.order_by(Ticket.priority, Ticket.created_at, Ticket.id).limit(limit).offset(offset)
    )
    return TicketPage(items=[TicketRead.model_validate(t) for t in rows], total=total)


@router.get("/{ticket_id}")
async def get_ticket(session: SessionDep, user: CurrentUser, ticket_id: int) -> TicketRead:
    return TicketRead.model_validate(await load_ticket(session, ticket_id, user))


@router.patch("/{ticket_id}")
async def update_ticket(
    session: SessionDep, user: CurrentUser, ticket_id: int, body: TicketUpdate
) -> TicketRead:
    ticket = await load_ticket(session, ticket_id, user)
    updates = body.model_dump(exclude_unset=True, exclude_none=True)

    if not is_staff(user):
        if ticket.status != TicketStatus.NEW:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ticket can no longer be edited")
        if updates.keys() & {"priority", "category"}:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only staff can change priority or category"
            )

    before = _snapshot(ticket)
    for field, value in updates.items():
        setattr(ticket, field, value)
    if ticket.priority != before["priority"]:
        sla.recompute(ticket)
    if changes := audit.diff(before, _snapshot(ticket)):
        audit.record(session, user, "ticket", ticket.id, "updated", changes)
    await session.commit()
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


def _apply_status(ticket: Ticket, target: TicketStatus) -> None:
    now = sla.utcnow()
    sla.on_status_change(ticket, ticket.status, target, now)
    ticket.status = target
    if target == TicketStatus.RESOLVED or (
        target == TicketStatus.CLOSED and ticket.resolved_at is None
    ):
        ticket.resolved_at = now  # closing straight from New also counts as the resolution
    elif target == TicketStatus.IN_PROGRESS:
        ticket.resolved_at = None  # reopened


@router.post("/{ticket_id}/status")
async def change_status(
    session: SessionDep, user: CurrentUser, ticket_id: int, body: StatusChange
) -> TicketRead:
    ticket = await load_ticket(session, ticket_id, user)
    if not can_transition(ticket.status, body.status, user.role):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot move ticket from {ticket.status} to {body.status}"
        )
    before = _snapshot(ticket)
    _apply_status(ticket, body.status)
    audit.record(
        session, user, "ticket", ticket.id, "status_changed", audit.diff(before, _snapshot(ticket))
    )
    await session.commit()
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.put("/{ticket_id}/assignee")
async def assign_ticket(
    session: SessionDep, user: StaffUser, ticket_id: int, body: AssigneeChange
) -> TicketRead:
    ticket = await load_ticket(session, ticket_id, user)
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Closed tickets cannot be reassigned")

    if body.assignee_id is not None:
        assignee = await _require_staff_user(session, body.assignee_id, "assignee")
        if not is_staff(assignee):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Assignee must be an agent")

    before = _snapshot(ticket)
    ticket.assignee_id = body.assignee_id
    # Picking a ticket up implies work has started.
    if body.assignee_id is not None and ticket.status == TicketStatus.NEW:
        _apply_status(ticket, TicketStatus.IN_PROGRESS)
    if changes := audit.diff(before, _snapshot(ticket)):
        audit.record(session, user, "ticket", ticket.id, "assigned", changes)
    await session.commit()
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


@router.get("/{ticket_id}/comments")
async def list_comments(
    session: SessionDep, user: CurrentUser, ticket_id: int
) -> list[CommentRead]:
    await load_ticket(session, ticket_id, user)
    stmt = select(TicketComment).where(TicketComment.ticket_id == ticket_id)
    if not is_staff(user):
        stmt = stmt.where(TicketComment.is_internal.is_(False))
    comments = await session.scalars(stmt.order_by(TicketComment.created_at, TicketComment.id))
    return [CommentRead.model_validate(c) for c in comments]


@router.post("/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    session: SessionDep, user: CurrentUser, ticket_id: int, body: CommentCreate
) -> CommentRead:
    ticket = await load_ticket(session, ticket_id, user)
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed")
    if body.is_internal and not is_staff(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff can add internal notes")

    comment = TicketComment(
        ticket_id=ticket.id, author_id=user.id, body=body.body, is_internal=body.is_internal
    )
    session.add(comment)
    await session.flush()
    changes: dict[str, object] = {"comment_id": comment.id, "is_internal": comment.is_internal}
    # The first public reply from staff (other than the requester) stops the response clock.
    if (
        is_staff(user)
        and not body.is_internal
        and user.id != ticket.requester_id
        and ticket.first_response_at is None
    ):
        ticket.first_response_at = sla.utcnow()
        changes["first_response"] = True
    audit.record(session, user, "ticket", ticket.id, "commented", changes)
    await session.commit()
    await session.refresh(comment)
    return CommentRead.model_validate(comment)


@router.get("/{ticket_id}/history")
async def ticket_history(
    session: SessionDep, user: StaffUser, ticket_id: int
) -> list[AuditLogRead]:
    await load_ticket(session, ticket_id, user)
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return [AuditLogRead.model_validate(r) for r in rows]
