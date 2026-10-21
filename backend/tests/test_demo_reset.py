"""The daily demo reset: when it may run, what it leaves behind, and the worker job around it."""

from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.core.config import Settings
from app.demo_articles import DEMO_ARTICLES
from app.demo_data import ADMIN, AGENT, DEMO_ASSETS, DEMO_TICKETS, DEMO_USERS
from app.models import Article, Asset, AuditLog, Role, Ticket, TicketComment, User
from app.seed import DemoResetRefused, reset_demo, seed
from app.services import sla
from app.worker import DEMO_RESET_HOUR, demo_reset, scheduled_jobs, sla_check

DEMO_ON = Settings(_env_file=None, seed_demo_data=True)
VISITOR_TICKET = "Visitor was here"


async def count(session, model):
    return await session.scalar(select(func.count()).select_from(model))


async def states(session, now):
    tickets = await session.scalars(select(Ticket).order_by(Ticket.id))
    return [(t.title, t.status, sla.overall_state(t, now)) for t in tickets]


async def headers_for(client, email):
    res = await client.post("/api/auth/login", data={"username": email, "password": "deskflow123"})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def yesterdays_demo(session):
    """A demo created a day ago and then used by visitors."""
    now = sla.utcnow() - timedelta(days=1)
    await seed(session, settings=DEMO_ON, now=now)
    return now


async def visit(client, session):
    """What visitors do: new records, changed records, a deleted article."""
    admin = await headers_for(client, ADMIN)
    agent = await headers_for(client, AGENT)
    res = await client.post(
        "/api/tickets",
        json={"title": VISITOR_TICKET, "description": "Hello", "category": "other"},
        headers=agent,
    )
    assert res.status_code == 201
    ticket_id = res.json()["id"]
    res = await client.post(
        f"/api/tickets/{ticket_id}/comments",
        json={"body": "hi", "is_internal": False},
        headers=agent,
    )
    assert res.status_code == 201
    first = await session.scalar(select(Ticket.id).order_by(Ticket.id))
    res = await client.patch(f"/api/tickets/{first}", json={"title": "Defaced"}, headers=agent)
    assert res.status_code == 200
    res = await client.post(
        "/api/assets", json={"type": "other", "manufacturer": "X", "model": "Y"}, headers=admin
    )
    assert res.status_code == 201
    article = await session.scalar(select(Article.id).order_by(Article.id))
    assert (await client.delete(f"/api/articles/{article}", headers=admin)).status_code == 204


@pytest.mark.parametrize(
    "settings",
    [
        Settings(_env_file=None),  # development default: demo data on, but the reset needs it said
        Settings(_env_file=None, seed_demo_data=False),
        Settings(_env_file=None, environment="production", jwt_secret="x" * 32),
    ],
    ids=["development-default", "switched-off", "production-default"],
)
async def test_refuses_unless_seed_demo_data_is_explicitly_true(session, yesterdays_demo, settings):
    before = await count(session, Ticket), await count(session, AuditLog)

    with pytest.raises(DemoResetRefused, match="SEED_DEMO_DATA"):
        await reset_demo(session, settings=settings)

    assert (await count(session, Ticket), await count(session, AuditLog)) == before


async def test_refuses_a_database_without_the_demo_accounts(session, people, client):
    _, headers = people["req"]
    res = await client.post(
        "/api/tickets",
        json={"title": "A real ticket", "description": "Real", "category": "other"},
        headers=headers,
    )
    assert res.status_code == 201

    with pytest.raises(DemoResetRefused, match="Not a demo database"):
        await reset_demo(session, settings=DEMO_ON)

    assert await count(session, Ticket) == 1
    assert await count(session, User) == 4  # nothing seeded either


async def test_refuses_when_a_demo_account_has_another_role(session, make_user):
    for email, _, role in DEMO_USERS:
        await make_user(Role.REQUESTER if role == Role.ADMIN else role, email)

    with pytest.raises(DemoResetRefused, match=ADMIN):
        await reset_demo(session, settings=DEMO_ON)


async def test_replaces_whatever_visitors_did_with_a_fresh_demo(session, client, yesterdays_demo):
    await visit(client, session)
    now = sla.utcnow()

    result = await reset_demo(session, settings=DEMO_ON, now=now)

    assert (result.tickets, result.assets, result.articles) == (
        len(DEMO_TICKETS),
        len(DEMO_ASSETS),
        len(DEMO_ARTICLES),
    )
    assert result.users == 0  # accounts are kept, not recreated
    titles = set(await session.scalars(select(Ticket.title)))
    assert titles == {t.title for t in DEMO_TICKETS}
    assert await count(session, Asset) == len(DEMO_ASSETS)
    assert set(await session.scalars(select(Article.title))) == {a.title for a in DEMO_ARTICLES}

    # Numbering starts over, so the demo looks the same every day.
    assert list(await session.scalars(select(Ticket.id).order_by(Ticket.id))) == list(
        range(1, len(DEMO_TICKETS) + 1)
    )
    tags = list(await session.scalars(select(Asset.asset_tag).order_by(Asset.asset_tag)))
    assert tags == [f"DF-{n:05d}" for n in range(1, len(DEMO_ASSETS) + 1)]


async def test_the_audit_log_is_restored_with_the_records_it_describes(
    session, client, yesterdays_demo
):
    await visit(client, session)
    now = sla.utcnow()

    await reset_demo(session, settings=DEMO_ON, now=now)

    # Only the fresh demo's own history: nothing about yesterday's or the visitors' records.
    entries = list(await session.scalars(select(AuditLog)))
    assert all(e.created_at <= now for e in entries)
    ticket_ids = set(await session.scalars(select(Ticket.id)))
    asset_ids = set(await session.scalars(select(Asset.id)))
    article_ids = set(await session.scalars(select(Article.id)))
    for e in entries:
        alive = {"ticket": ticket_ids, "asset": asset_ids, "article": article_ids}[e.entity_type]
        assert e.entity_id in alive
    assert not any(e.changes.get("title") == VISITOR_TICKET for e in entries)


async def test_the_result_is_fresh_relative_to_the_time_of_the_reset(session, yesterdays_demo):
    created_then = await states(session, yesterdays_demo)
    now = sla.utcnow()

    # A day later the old copy has drifted: more tickets breached than the demo was made with.
    drifted = Counter(state for _, _, state in await states(session, now))
    assert (
        drifted[sla.SlaState.BREACHED] > Counter(s for *_, s in created_then)[sla.SlaState.BREACHED]
    )

    await reset_demo(session, settings=DEMO_ON, now=now)

    assert await states(session, now) == created_then


async def test_is_idempotent(session, yesterdays_demo):
    now = sla.utcnow()
    await reset_demo(session, settings=DEMO_ON, now=now)
    first = [await count(session, m) for m in (Ticket, TicketComment, Asset, Article, AuditLog)]

    await reset_demo(session, settings=DEMO_ON, now=now)

    assert [await count(session, m) for m in (Ticket, TicketComment, Asset, Article, AuditLog)] == (
        first
    )


async def test_keeps_every_account(session, make_user, yesterdays_demo):
    owner = await make_user(Role.ADMIN, "owner@example.com")
    users = await count(session, User)

    await reset_demo(session, settings=DEMO_ON)

    assert await count(session, User) == users
    assert await session.scalar(select(User.id).where(User.email == "owner@example.com")) == (
        owner.id
    )


async def test_also_creates_the_demo_from_scratch(session, make_user):
    for email, _, role in DEMO_USERS:
        await make_user(role, email)

    result = await reset_demo(session, settings=DEMO_ON)

    assert result.tickets == len(DEMO_TICKETS)


# The worker


def test_the_worker_only_schedules_the_reset_when_demo_data_is_on():
    (job,) = scheduled_jobs(Settings(_env_file=None))
    assert job.coroutine is sla_check

    check, reset = scheduled_jobs(DEMO_ON)
    assert check.coroutine is sla_check
    assert reset.coroutine is demo_reset
    assert (reset.hour, reset.second) == (DEMO_RESET_HOUR, 0)
    assert reset.run_at_startup is False  # a restart must not wipe a visitor's session


async def test_the_reset_job_checks_again_and_skips_when_off(monkeypatch):
    # Even if it were scheduled, the job itself refuses without SEED_DEMO_DATA=true.
    monkeypatch.setattr("app.seed.get_settings", lambda: Settings(_env_file=None))
    assert (await demo_reset({})).startswith("skipped")
