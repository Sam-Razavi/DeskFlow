from datetime import timedelta

from app.models import Priority, TicketStatus
from tests.test_sla_monitor import NOW, H, add_ticket


async def summary(client, headers):
    res = await client.get("/api/dashboard", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def test_requires_authentication(client):
    assert (await client.get("/api/dashboard")).status_code == 401


async def test_staff_summary(client, session, people):
    req, _ = people["req"]
    agent, agent_headers = people["agent"]
    # sla.utcnow() is the real clock, so build ages relative to it rather than the NOW constant.
    from app.services import sla

    shift = sla.utcnow() - NOW
    base = dict(requester=req)

    async def add(**kw):
        ticket = await add_ticket(session, base["requester"], **kw)
        # Re-anchor to the real clock.
        ticket.created_at += shift
        ticket.response_due_at += shift
        ticket.resolution_due_at += shift
        if ticket.first_response_at:
            ticket.first_response_at += shift
        return ticket

    await add(age=timedelta(minutes=10), priority=Priority.P1)  # open, ok, unassigned
    await add(age=9 * H, priority=Priority.P2, assignee_id=agent.id)  # breached, mine
    await add(age=7 * H, priority=Priority.P2, first_response_at=NOW - 6 * H)  # at risk
    await add(age=3 * H, priority=Priority.P3, status=TicketStatus.RESOLVED, resolved_at=NOW - H)
    await add(age=3 * H, priority=Priority.P4, status=TicketStatus.CLOSED, resolved_at=NOW - H)
    await session.flush()

    data = await summary(client, agent_headers)

    assert data["open_total"] == 3
    assert data["open_by_priority"] == {"p1": 1, "p2": 2, "p3": 0, "p4": 0}
    assert data["sla_breached"] == 1
    assert data["sla_at_risk"] == 1
    assert data["unassigned"] == 2
    assert data["assigned_to_me"] == 1
    assert data["awaiting_confirmation"] == 1


async def test_requesters_only_see_their_own_figures(client, people):
    from tests.test_tickets import create

    _, req_headers = people["req"]
    _, other_headers = people["other"]
    await create(client, req_headers)
    await create(client, other_headers)
    await create(client, other_headers)

    assert (await summary(client, req_headers))["open_total"] == 1
    assert (await summary(client, other_headers))["open_total"] == 2


async def test_sla_list_filter_uses_the_same_rules(client, session, people):
    from app.services import sla
    from tests.test_tickets import create

    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    healthy = await create(client, req_headers, title="Healthy ticket")

    overdue = await add_ticket(session, req, age=timedelta(hours=1), priority=Priority.P1)
    overdue.created_at = sla.utcnow() - 10 * H
    overdue.response_due_at, overdue.resolution_due_at = sla.due_dates(
        overdue.created_at, Priority.P1
    )
    await session.flush()

    breached = (await client.get("/api/tickets?sla=breached", headers=agent_headers)).json()
    assert [t["id"] for t in breached["items"]] == [overdue.id]
    assert breached["items"][0]["sla_state"] == "breached"
    assert healthy["id"] not in [t["id"] for t in breached["items"]]

    nothing = (await client.get("/api/tickets?sla=at_risk", headers=agent_headers)).json()
    assert nothing["items"] == []
    assert (await client.get("/api/tickets?sla=bogus", headers=agent_headers)).status_code == 422


async def test_summary_includes_equipment_figures_for_staff_only(client, people):
    from datetime import UTC, datetime, timedelta

    from tests.test_assets import create_asset, set_status

    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    soon = (datetime.now(UTC).date() + timedelta(days=5)).isoformat()
    repair = await create_asset(client, agent_headers, serial_number="1")
    expiring = await create_asset(
        client, agent_headers, serial_number="2", warranty_expires_on=soon
    )
    retired = await create_asset(client, agent_headers, serial_number="3", warranty_expires_on=soon)
    await set_status(client, agent_headers, repair["id"], "in_repair")
    await set_status(client, agent_headers, retired["id"], "retired")
    assert expiring["warranty_state"] == "expiring"

    staff = await summary(client, agent_headers)
    assert staff["assets_in_repair"] == 1
    assert staff["warranty_expiring"] == 1  # the retired one no longer counts

    requester = await summary(client, req_headers)
    assert requester["assets_in_repair"] == 0
    assert requester["warranty_expiring"] == 0
    assert req.id
