from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models.audit import AuditLog
from app.models.ticket import Category, Priority, Ticket, TicketComment, TicketStatus
from app.models.user import Role, User
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
from app.services import audit
from app.services.workflow import can_transition

router = APIRouter(prefix="/tickets", tags=["tickets"])

STAFF_ROLES = (Role.AGENT, Role.ADMIN)
StaffUser = Annotated[User, Depends(require_roles(*STAFF_ROLES))]

TRACKED_FIELDS = ("title", "description", "status", "priority", "category", "assignee_id")


def _is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


def _snapshot(ticket: Ticket) -> dict[str, object]:
    return {f: getattr(ticket, f) for f in TRACKED_FIELDS}


async def _get_ticket(session: AsyncSession, ticket_id: int, user: User) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    # Requesters get a 404 (not 403) for other people's tickets so ids can't be probed.
    if ticket is None or (not _is_staff(user) and ticket.requester_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket


async def _require_staff_user(session: AsyncSession, user_id: int, what: str) -> User:
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Unknown {what}")
    return user


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_ticket(session: SessionDep, user: CurrentUser, body: TicketCreate) -> TicketRead:
    requester_id = user.id
    if _is_staff(user) and body.requester_id is not None:
        requester_id = (await _require_staff_user(session, body.requester_id, "requester")).id

    ticket = Ticket(
        title=body.title,
        description=body.description,
        priority=body.priority,
        category=body.category,
        requester_id=requester_id,
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
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TicketPage:
    stmt = select(Ticket)
    if not _is_staff(user):
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
    return TicketRead.model_validate(await _get_ticket(session, ticket_id, user))


@router.patch("/{ticket_id}")
async def update_ticket(
    session: SessionDep, user: CurrentUser, ticket_id: int, body: TicketUpdate
) -> TicketRead:
    ticket = await _get_ticket(session, ticket_id, user)
    updates = body.model_dump(exclude_unset=True, exclude_none=True)

    if not _is_staff(user):
        if ticket.status != TicketStatus.NEW:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Ticket can no longer be edited")
        if updates.keys() & {"priority", "category"}:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Only staff can change priority or category"
            )

    before = _snapshot(ticket)
    for field, value in updates.items():
        setattr(ticket, field, value)
    if changes := audit.diff(before, _snapshot(ticket)):
        audit.record(session, user, "ticket", ticket.id, "updated", changes)
    await session.commit()
    await session.refresh(ticket)
    return TicketRead.model_validate(ticket)


def _apply_status(ticket: Ticket, target: TicketStatus) -> None:
    ticket.status = target
    if target == TicketStatus.RESOLVED:
        ticket.resolved_at = datetime.now(UTC)
    elif target == TicketStatus.IN_PROGRESS:
        ticket.resolved_at = None  # reopened


@router.post("/{ticket_id}/status")
async def change_status(
    session: SessionDep, user: CurrentUser, ticket_id: int, body: StatusChange
) -> TicketRead:
    ticket = await _get_ticket(session, ticket_id, user)
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
    ticket = await _get_ticket(session, ticket_id, user)
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Closed tickets cannot be reassigned")

    if body.assignee_id is not None:
        assignee = await _require_staff_user(session, body.assignee_id, "assignee")
        if not _is_staff(assignee):
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
    await _get_ticket(session, ticket_id, user)
    stmt = select(TicketComment).where(TicketComment.ticket_id == ticket_id)
    if not _is_staff(user):
        stmt = stmt.where(TicketComment.is_internal.is_(False))
    comments = await session.scalars(stmt.order_by(TicketComment.created_at, TicketComment.id))
    return [CommentRead.model_validate(c) for c in comments]


@router.post("/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
async def add_comment(
    session: SessionDep, user: CurrentUser, ticket_id: int, body: CommentCreate
) -> CommentRead:
    ticket = await _get_ticket(session, ticket_id, user)
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed")
    if body.is_internal and not _is_staff(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only staff can add internal notes")

    comment = TicketComment(
        ticket_id=ticket.id, author_id=user.id, body=body.body, is_internal=body.is_internal
    )
    session.add(comment)
    await session.flush()
    audit.record(
        session,
        user,
        "ticket",
        ticket.id,
        "commented",
        {"comment_id": comment.id, "is_internal": comment.is_internal},
    )
    await session.commit()
    await session.refresh(comment)
    return CommentRead.model_validate(comment)


@router.get("/{ticket_id}/history")
async def ticket_history(
    session: SessionDep, user: StaffUser, ticket_id: int
) -> list[AuditLogRead]:
    await _get_ticket(session, ticket_id, user)
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "ticket", AuditLog.entity_id == ticket_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return [AuditLogRead.model_validate(r) for r in rows]
