"""Finds tickets that have crossed an SLA threshold and records it, once, in the audit log."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.services import audit, sla
from app.services.sla import SlaState


async def check_sla(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Flag open, running tickets that are at risk or breached; return counts of new flags.

    The *_at columns make this idempotent: a threshold is audited the first time it is seen and
    never again, so running every minute does not spam the log. Paused tickets are skipped because
    their clock is stopped.
    """
    now = now or sla.utcnow()
    newly = {"resolution_at_risk": 0, "resolution_breached": 0, "response_breached": 0}

    tickets = await session.scalars(
        select(Ticket).where(
            Ticket.status.not_in(sla.DONE_STATUSES), Ticket.sla_paused_at.is_(None)
        )
    )
    for ticket in tickets:
        resolution = sla.resolution_state(ticket, now)
        response = sla.response_state(ticket, now)

        if resolution == SlaState.BREACHED and ticket.resolution_breached_at is None:
            ticket.resolution_breached_at = now
            _log(session, ticket, "sla_breached", "resolution")
            newly["resolution_breached"] += 1
        elif resolution == SlaState.AT_RISK and ticket.resolution_at_risk_at is None:
            ticket.resolution_at_risk_at = now
            _log(session, ticket, "sla_at_risk", "resolution")
            newly["resolution_at_risk"] += 1

        if response == SlaState.BREACHED and ticket.response_breached_at is None:
            ticket.response_breached_at = now
            _log(session, ticket, "sla_breached", "response")
            newly["response_breached"] += 1

    await session.commit()
    return newly


def _log(session: AsyncSession, ticket: Ticket, action: str, kind: str) -> None:
    # No actor: the system, not a person, made this observation.
    audit.record(session, None, "ticket", ticket.id, action, {"kind": kind})
