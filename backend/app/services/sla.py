"""SLA rules: targets per priority, pausing while a ticket waits on the requester, and the
single place that decides whether a ticket is on track, at risk or breached.

Times are wall-clock (not business hours) to keep the rules easy to follow.
"""

import enum
from datetime import UTC, datetime, timedelta
from typing import NamedTuple, Protocol

from app.models.ticket import Priority, TicketStatus


class SlaTarget(NamedTuple):
    response: timedelta
    resolution: timedelta


TARGETS: dict[Priority, SlaTarget] = {
    Priority.P1: SlaTarget(timedelta(hours=1), timedelta(hours=4)),
    Priority.P2: SlaTarget(timedelta(hours=4), timedelta(hours=8)),
    Priority.P3: SlaTarget(timedelta(hours=8), timedelta(hours=24)),
    Priority.P4: SlaTarget(timedelta(hours=24), timedelta(hours=72)),
}

# A ticket is "at risk" once this share of its resolution window has elapsed.
AT_RISK_FRACTION = 0.75

DONE_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)


class SlaState(enum.StrEnum):
    OK = "ok"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    MET = "met"
    PAUSED = "paused"
    NOT_APPLICABLE = "n/a"


# Used to pick the single most important state to show for a ticket.
_SEVERITY = {
    SlaState.BREACHED: 5,
    SlaState.AT_RISK: 4,
    SlaState.PAUSED: 3,
    SlaState.OK: 2,
    SlaState.MET: 1,
    SlaState.NOT_APPLICABLE: 0,
}


class SlaFields(Protocol):
    """The ticket attributes the rules read; satisfied by the ORM model and by query rows."""

    status: TicketStatus
    created_at: datetime
    resolved_at: datetime | None
    first_response_at: datetime | None
    response_due_at: datetime
    resolution_due_at: datetime
    sla_paused_at: datetime | None


class MutableSlaFields(SlaFields, Protocol):
    priority: Priority
    sla_paused_seconds: int


def due_dates(
    created_at: datetime, priority: Priority, paused_seconds: int = 0
) -> tuple[datetime, datetime]:
    """Return (response_due_at, resolution_due_at), pushed back by any time already paused."""
    target = TARGETS[priority]
    paused = timedelta(seconds=paused_seconds)
    return created_at + target.response + paused, created_at + target.resolution + paused


def recompute(ticket: MutableSlaFields) -> None:
    """Re-derive the due dates after a priority change. A response already given is left alone."""
    response_due, resolution_due = due_dates(
        ticket.created_at, ticket.priority, ticket.sla_paused_seconds
    )
    if ticket.first_response_at is None:
        ticket.response_due_at = response_due
    ticket.resolution_due_at = resolution_due


def on_status_change(
    ticket: MutableSlaFields, old: TicketStatus, new: TicketStatus, now: datetime
) -> None:
    """Stop the clock when a ticket goes Pending and restart it, pushing the deadlines back by the
    time spent waiting, when it leaves Pending."""
    if new == TicketStatus.PENDING:
        if ticket.sla_paused_at is None:
            ticket.sla_paused_at = now
    elif old == TicketStatus.PENDING and ticket.sla_paused_at is not None:
        waited = now - ticket.sla_paused_at
        ticket.sla_paused_seconds += int(waited.total_seconds())
        ticket.sla_paused_at = None
        ticket.resolution_due_at += waited
        # Shifting a response deadline that was already answered would rewrite history.
        if ticket.first_response_at is None:
            ticket.response_due_at += waited


def register_reply(
    ticket: MutableSlaFields, now: datetime, *, by_staff: bool, by_requester: bool, internal: bool
) -> bool:
    """Stop the response clock if this comment is the first public reply from staff (not an
    internal note, and not the requester answering themselves). Return whether it did."""
    if by_staff and not internal and not by_requester and ticket.first_response_at is None:
        ticket.first_response_at = now
        return True
    return False


def _running_state(created_at: datetime, due: datetime, now: datetime) -> SlaState:
    if now > due:
        return SlaState.BREACHED
    if now >= due - (due - created_at) * (1 - AT_RISK_FRACTION):
        return SlaState.AT_RISK
    return SlaState.OK


def resolution_state(ticket: SlaFields, now: datetime) -> SlaState:
    if ticket.status in DONE_STATUSES:
        done_at = ticket.resolved_at or now
        return SlaState.MET if done_at <= ticket.resolution_due_at else SlaState.BREACHED
    if ticket.sla_paused_at is not None:
        return SlaState.PAUSED
    return _running_state(ticket.created_at, ticket.resolution_due_at, now)


def response_state(ticket: SlaFields, now: datetime) -> SlaState:
    if ticket.first_response_at is not None:
        met = ticket.first_response_at <= ticket.response_due_at
        return SlaState.MET if met else SlaState.BREACHED
    if ticket.status in DONE_STATUSES:
        return SlaState.NOT_APPLICABLE  # resolved without ever needing a reply
    if ticket.sla_paused_at is not None:
        return SlaState.PAUSED
    return _running_state(ticket.created_at, ticket.response_due_at, now)


def overall_state(ticket: SlaFields, now: datetime) -> SlaState:
    states = (response_state(ticket, now), resolution_state(ticket, now))
    return max(states, key=_SEVERITY.__getitem__)


def utcnow() -> datetime:
    return datetime.now(UTC)
