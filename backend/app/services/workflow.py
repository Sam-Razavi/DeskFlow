from datetime import datetime

from app.models.ticket import Ticket
from app.models.ticket import TicketStatus as S
from app.models.user import Role
from app.services import sla

TRANSITIONS: dict[S, set[S]] = {
    S.NEW: {S.IN_PROGRESS, S.PENDING, S.RESOLVED, S.CLOSED},
    S.IN_PROGRESS: {S.PENDING, S.RESOLVED},
    S.PENDING: {S.IN_PROGRESS, S.RESOLVED},
    S.RESOLVED: {S.IN_PROGRESS, S.CLOSED},  # reopen or confirm
    S.CLOSED: set(),
}

# What a requester may do to their own ticket: confirm a fix or reopen it.
REQUESTER_TRANSITIONS: set[tuple[S, S]] = {(S.RESOLVED, S.CLOSED), (S.RESOLVED, S.IN_PROGRESS)}


def can_transition(current: S, target: S, role: Role) -> bool:
    if target not in TRANSITIONS[current]:
        return False
    if role == Role.REQUESTER:
        return (current, target) in REQUESTER_TRANSITIONS
    return True


def apply_status(ticket: Ticket, target: S, now: datetime) -> None:
    """Move a ticket to `target` (already checked with can_transition), keeping the SLA clock and
    the resolution time in step."""
    sla.on_status_change(ticket, ticket.status, target, now)
    ticket.status = target
    if target == S.RESOLVED or (target == S.CLOSED and ticket.resolved_at is None):
        ticket.resolved_at = now  # closing straight from New also counts as the resolution
    elif target == S.IN_PROGRESS:
        ticket.resolved_at = None  # reopened


def assign(ticket: Ticket, assignee_id: int | None, now: datetime) -> None:
    ticket.assignee_id = assignee_id
    # Picking a ticket up implies work has started.
    if assignee_id is not None and ticket.status == S.NEW:
        apply_status(ticket, S.IN_PROGRESS, now)
