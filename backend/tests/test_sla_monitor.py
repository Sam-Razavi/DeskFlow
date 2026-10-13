from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AuditLog, Priority, Ticket, TicketStatus
from app.services import sla
from app.services.sla_monitor import check_sla

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)
H = timedelta(hours=1)


async def add_ticket(session, requester, *, age, priority=Priority.P2, **fields):
    created = NOW - age
    response_due, resolution_due = sla.due_dates(created, priority)
    ticket = Ticket(
        title="t",
        description="d",
        priority=priority,
        category="other",
        requester_id=requester.id,
        created_at=created,
        response_due_at=response_due,
        resolution_due_at=resolution_due,
        **fields,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def audit_actions(session, ticket):
    rows = await session.scalars(
        select(AuditLog).where(AuditLog.entity_id == ticket.id).order_by(AuditLog.id)
    )
    return [(r.action, r.changes, r.actor_id) for r in rows]


async def test_flags_a_ticket_that_is_at_risk(session, people):
    req, _ = people["req"]
    ticket = await add_ticket(session, req, age=7 * H, first_response_at=NOW - 6 * H)  # P2: 8h

    newly = await check_sla(session, NOW)

    assert newly == {"resolution_at_risk": 1, "resolution_breached": 0, "response_breached": 0}
    assert ticket.resolution_at_risk_at == NOW
    assert await audit_actions(session, ticket) == [("sla_at_risk", {"kind": "resolution"}, None)]


async def test_flags_breaches_of_both_clocks(session, people):
    req, _ = people["req"]
    ticket = await add_ticket(session, req, age=9 * H)  # never answered; P2 is 4h / 8h

    newly = await check_sla(session, NOW)

    assert newly["resolution_breached"] == 1
    assert newly["response_breached"] == 1
    kinds = {(a, c["kind"]) for a, c, _ in await audit_actions(session, ticket)}
    assert kinds == {("sla_breached", "resolution"), ("sla_breached", "response")}


async def test_each_threshold_is_only_logged_once(session, people):
    req, _ = people["req"]
    ticket = await add_ticket(session, req, age=9 * H)

    await check_sla(session, NOW)
    second = await check_sla(session, NOW + H)

    assert not any(second.values())
    assert len(await audit_actions(session, ticket)) == 2


async def test_leaves_healthy_paused_and_finished_tickets_alone(session, people):
    req, _ = people["req"]
    healthy = await add_ticket(session, req, age=1 * H)
    paused = await add_ticket(
        session, req, age=50 * H, status=TicketStatus.PENDING, sla_paused_at=NOW - 40 * H
    )
    resolved = await add_ticket(
        session, req, age=50 * H, status=TicketStatus.RESOLVED, resolved_at=NOW - 45 * H
    )
    closed = await add_ticket(
        session, req, age=50 * H, status=TicketStatus.CLOSED, resolved_at=NOW - 45 * H
    )

    newly = await check_sla(session, NOW)

    assert not any(newly.values())
    for ticket in (healthy, paused, resolved, closed):
        assert await audit_actions(session, ticket) == []


async def test_a_paused_ticket_is_flagged_once_it_resumes_and_runs_out_of_time(session, people):
    req, _ = people["req"]
    ticket = await add_ticket(
        session, req, age=20 * H, status=TicketStatus.PENDING, sla_paused_at=NOW - 10 * H
    )
    await check_sla(session, NOW)
    assert await audit_actions(session, ticket) == []

    # Resume with the 10h wait pushing the 8h deadline to 18h after creation: still ahead.
    sla.on_status_change(ticket, TicketStatus.PENDING, TicketStatus.IN_PROGRESS, NOW)
    ticket.status = TicketStatus.IN_PROGRESS
    await check_sla(session, NOW)
    assert ticket.resolution_breached_at == NOW  # 20h old vs 18h deadline


def test_worker_runs_the_check_every_minute_and_at_startup():
    from app.worker import WorkerSettings, sla_check

    (job,) = WorkerSettings.cron_jobs
    assert job.coroutine is sla_check
    assert job.second == 0
    assert job.run_at_startup is True
