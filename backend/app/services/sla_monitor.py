"""Finds tickets that have crossed an SLA threshold and records it, once, in the audit log."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.services import audit, sla
from app.services.sla import SlaState

FLAGS = ("resolution_at_risk", "resolution_breached", "response_breached")


async def check_sla(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Flag open, running tickets that are at risk or breached; return counts of new flags.

    The *_at columns make this idempotent: a threshold is audited the first time it is seen and
    never again, so running every minute does not spam the log. Paused tickets are skipped because
    their clock is stopped.
    """
    now = now or sla.utcnow()
    newly = dict.fromkeys(FLAGS, 0)

    tickets = await session.scalars(
        select(Ticket).where(
            Ticket.status.not_in(sla.DONE_STATUSES), Ticket.sla_paused_at.is_(None)
        )
    )
    for ticket in tickets:
        for flag in flag_ticket(session, ticket, now):
            newly[flag] += 1

    await session.commit()
    return newly


def flag_ticket(session: AsyncSession, ticket: Ticket, now: datetime) -> list[str]:
    """One ticket's part of a check at `now`: set and audit each threshold it has newly crossed.

    Returns the flags it set (names from FLAGS). The worker runs this for every open ticket each
    minute; the demo seed replays it over the history it writes, so seeded tickets carry exactly
    the flags the worker would have set.
    """
    if ticket.status in sla.DONE_STATUSES or ticket.sla_paused_at is not None:
        return []  # finished, or the clock is stopped

    flagged = []
    resolution = sla.resolution_state(ticket, now)
    response = sla.response_state(ticket, now)

    if resolution == SlaState.BREACHED and ticket.resolution_breached_at is None:
        ticket.resolution_breached_at = now
        _log(session, ticket, "sla_breached", "resolution", now)
        flagged.append("resolution_breached")
    elif resolution == SlaState.AT_RISK and ticket.resolution_at_risk_at is None:
        ticket.resolution_at_risk_at = now
        _log(session, ticket, "sla_at_risk", "resolution", now)
        flagged.append("resolution_at_risk")

    if response == SlaState.BREACHED and ticket.response_breached_at is None:
        ticket.response_breached_at = now
        _log(session, ticket, "sla_breached", "response", now)
        flagged.append("response_breached")

    return flagged


def _log(session: AsyncSession, ticket: Ticket, action: str, kind: str, now: datetime) -> None:
    # No actor: the system, not a person, made this observation.
    audit.record(session, None, "ticket", ticket.id, action, {"kind": kind}, at=now)
