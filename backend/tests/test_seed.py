"""The demo seed: what it creates, that it is idempotent, and that it follows the app's rules."""

import re
from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.demo_articles import DEMO_ARTICLES
from app.demo_data import (
    ADMIN,
    AGENT,
    DEMO_ASSETS,
    DEMO_PASSWORD,
    DEMO_REQUESTERS,
    DEMO_TICKETS,
    DEMO_USERS,
    GRACE,
)
from app.models import (
    Article,
    Asset,
    AssetStatus,
    AuditLog,
    Category,
    Priority,
    Role,
    Ticket,
    TicketComment,
    TicketStatus,
    User,
)
from app.schemas.asset import AssetCreate
from app.schemas.ticket import CommentCreate, TicketCreate
from app.seed import seed
from app.services import sla
from app.services.sla import SlaState
from app.services.sla_monitor import check_sla

DEMO_ON = Settings(_env_file=None, seed_demo_data=True)


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


async def login(client, email, password=DEMO_PASSWORD):
    return await client.post("/api/auth/login", data={"username": email, "password": password})


async def headers_for(client, email):
    res = await login(client, email)
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def seeded(session):
    now = sla.utcnow()
    result = await seed(session, settings=DEMO_ON, now=now)
    return result, now


async def test_creates_accounts_articles_tickets_and_equipment(session, seeded):
    result, _ = seeded
    assert result.users == len(DEMO_USERS) + len(DEMO_REQUESTERS)
    assert result.articles == len(DEMO_ARTICLES)
    assert result.tickets == len(DEMO_TICKETS) == await count(session, Ticket)
    assert result.assets == len(DEMO_ASSETS) == await count(session, Asset)
    assert 15 <= result.tickets <= 20
    assert 12 <= result.assets <= 15

    roles = {email: role for email, role in await session.execute(select(User.email, User.role))}
    for email, _, role in DEMO_USERS:
        assert roles[email] == role
    for email, _ in DEMO_REQUESTERS:
        assert roles[email] == Role.REQUESTER

    notes = await session.scalar(
        select(func.count()).select_from(TicketComment).where(TicketComment.is_internal)
    )
    assert notes >= 3
    assert await count(session, TicketComment) > notes


async def test_documented_accounts_sign_in_and_the_extra_colleagues_cannot(client, seeded):
    for email, _, _ in DEMO_USERS:
        assert (await login(client, email)).status_code == 200
    for email, _ in DEMO_REQUESTERS:
        assert (await login(client, email)).status_code == 401


async def test_running_it_again_creates_nothing(session, seeded):
    _, now = seeded
    before = {m: await count(session, m) for m in (User, Article, Ticket, Asset, AuditLog)}

    again = await seed(session, settings=DEMO_ON, now=now + timedelta(days=1))

    assert again is not None
    assert (again.users, again.articles, again.tickets, again.assets) == (0, 0, 0, 0)
    assert {m: await count(session, m) for m in before} == before


async def test_existing_demo_accounts_are_never_changed(session, make_user):
    agent = await make_user(Role.ADMIN, AGENT)  # e.g. promoted by hand
    await seed(session, settings=DEMO_ON)
    await session.refresh(agent)
    assert agent.role == Role.ADMIN
    assert agent.full_name == "Test Admin"


@pytest.mark.parametrize(
    "settings",
    [
        Settings(_env_file=None, seed_demo_data=False),
        Settings(_env_file=None, environment="production", jwt_secret="x" * 32),
    ],
    ids=["switched-off", "production-default"],
)
async def test_nothing_is_created_when_demo_data_is_off(session, settings):
    assert await seed(session, settings=settings) is None
    for model in (User, Article, Ticket, Asset, AuditLog):
        assert await count(session, model) == 0


async def test_sample_tickets_never_mix_into_a_helpdesk_in_use(session, people, client):
    _, headers = people["req"]
    res = await client.post(
        "/api/tickets",
        json={"title": "A real ticket", "description": "Real", "category": "other"},
        headers=headers,
    )
    assert res.status_code == 201

    result = await seed(session, settings=DEMO_ON)

    assert (result.tickets, result.assets) == (0, 0)
    assert await count(session, Ticket) == 1
    assert await count(session, Asset) == 0


async def test_covers_every_category_priority_and_status(session, seeded):
    tickets = list(await session.scalars(select(Ticket)))
    assert {t.category for t in tickets} == set(Category)
    assert {t.priority for t in tickets} == set(Priority)
    assert {t.status for t in tickets} == set(TicketStatus)
    assert any(t.assignee_id is None for t in tickets if t.status == TicketStatus.NEW)

    assets = list(await session.scalars(select(Asset)))
    assert {a.status for a in assets} == set(AssetStatus)


async def test_sla_states_make_an_interesting_dashboard(session, seeded):
    """Judged by the real rules, at the moment of seeding."""
    _, now = seeded
    tickets = list(await session.scalars(select(Ticket)))
    open_states = Counter(
        sla.overall_state(t, now) for t in tickets if t.status not in sla.DONE_STATUSES
    )
    assert open_states[SlaState.BREACHED] == 2
    assert open_states[SlaState.AT_RISK] == 2
    assert open_states[SlaState.PAUSED] == 2
    assert open_states[SlaState.OK] >= 5

    done = Counter(sla.resolution_state(t, now) for t in tickets if t.status in sla.DONE_STATUSES)
    assert done[SlaState.MET] >= 5
    assert done[SlaState.BREACHED] == 1  # one was resolved late, as happens


async def test_the_worker_finds_nothing_left_to_flag(session, seeded):
    """The replayed monitor recorded exactly what the worker would have: running the real check
    at the same moment adds nothing."""
    _, now = seeded
    assert await check_sla(session, now) == {
        "resolution_at_risk": 0,
        "resolution_breached": 0,
        "response_breached": 0,
    }


async def test_sla_flags_and_their_audit_entries_agree(session, seeded):
    _, now = seeded
    entries = await session.scalars(select(AuditLog).where(AuditLog.action.like("sla_%")))
    logged = {(e.entity_id, e.action, e.changes["kind"]): e.created_at for e in entries}
    assert logged, "some tickets crossed a threshold"

    markers = {
        ("sla_at_risk", "resolution"): "resolution_at_risk_at",
        ("sla_breached", "resolution"): "resolution_breached_at",
        ("sla_breached", "response"): "response_breached_at",
    }
    for ticket in await session.scalars(select(Ticket)):
        for (action, kind), column in markers.items():
            marked = getattr(ticket, column)
            assert logged.get((ticket.id, action, kind)) == marked
            if marked is not None:
                assert marked <= now and marked.second == 0  # on a worker run, at a whole minute
                assert marked >= ticket.created_at


async def test_every_record_has_a_history_that_starts_with_its_creation(session, seeded):
    _, now = seeded
    rows = list(await session.scalars(select(AuditLog).order_by(AuditLog.created_at, AuditLog.id)))
    assert all(r.created_at <= now for r in rows)

    first: dict[tuple[str, int], str] = {}
    for r in rows:
        first.setdefault((r.entity_type, r.entity_id), r.action)
    for ticket in await session.scalars(select(Ticket)):
        assert first[("ticket", ticket.id)] == "created"
    for asset in await session.scalars(select(Asset)):
        assert first[("asset", asset.id)] == "created"

    comments = await count(session, TicketComment)
    assert sum(r.action == "commented" for r in rows) == comments


async def test_dates_follow_the_story(session, seeded):
    _, now = seeded
    for t in await session.scalars(select(Ticket)):
        assert t.created_at <= t.updated_at <= now
        if t.first_response_at:
            assert t.created_at < t.first_response_at <= now
        if t.status in sla.DONE_STATUSES:
            assert t.resolved_at is not None and t.created_at < t.resolved_at <= now
        else:
            assert t.resolved_at is None
    for c in await session.scalars(select(TicketComment)):
        ticket = await session.get(Ticket, c.ticket_id)
        assert ticket.created_at < c.created_at <= now


async def test_demo_text_and_equipment_pass_the_api_validation(session, seeded):
    for t in DEMO_TICKETS:
        TicketCreate(title=t.title, description=t.description)
        for step in t.steps:
            if hasattr(step, "body"):
                CommentCreate(body=step.body)
    for a in await session.scalars(select(Asset)):
        AssetCreate(
            type=a.type,
            manufacturer=a.manufacturer,
            model=a.model,
            serial_number=a.serial_number,
            location=a.location,
            purchase_date=a.purchase_date,
            warranty_expires_on=a.warranty_expires_on,
            notes=a.notes,
        )


async def test_asset_tags_come_from_the_shared_sequence(session, client, seeded):
    tags = sorted(await session.scalars(select(Asset.asset_tag)))
    assert all(re.fullmatch(r"DF-\d{5}", tag) for tag in tags)

    # The API carries on from the same sequence, so a new asset never collides with the demo.
    res = await client.post(
        "/api/assets",
        json={"type": "laptop", "manufacturer": "Acme", "model": "Book"},
        headers=await headers_for(client, ADMIN),
    )
    assert res.status_code == 201, res.text
    assert res.json()["asset_tag"] > tags[-1]


async def test_the_dashboard_through_the_api(client, seeded):
    res = await client.get("/api/dashboard", headers=await headers_for(client, AGENT))
    assert res.status_code == 200
    data = res.json()

    assert data["open_total"] == 12
    assert data["sla_breached"] == 2
    assert data["sla_at_risk"] == 2
    assert data["unassigned"] == 3
    assert data["assigned_to_me"] == 8
    assert data["awaiting_confirmation"] == 2
    assert data["assets_in_repair"] == 2
    assert data["warranty_expiring"] == 2


async def test_the_demo_requester_has_tickets_and_equipment_of_their_own(client, seeded):
    headers = await headers_for(client, GRACE)

    tickets = (await client.get("/api/tickets", headers=headers)).json()
    assert tickets["total"] == 3

    assets = (await client.get("/api/assets", headers=headers)).json()
    assert assets["total"] == 2

    # Internal notes stay internal on the seeded tickets too.
    for ticket in tickets["items"]:
        comments = (
            await client.get(f"/api/tickets/{ticket['id']}/comments", headers=headers)
        ).json()
        assert not any(c["is_internal"] for c in comments)


async def test_staff_can_work_with_the_seeded_tickets(client, session, seeded):
    headers = await headers_for(client, AGENT)
    queue = await client.get("/api/tickets", params={"unassigned": True}, headers=headers)
    ticket = queue.json()["items"][0]

    res = await client.put(
        f"/api/tickets/{ticket['id']}/assignee",
        json={"assignee_id": (await session.scalar(select(User.id).where(User.email == AGENT)))},
        headers=headers,
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"
