"""The daily demo reset: when it may run, what it leaves behind, and the worker job around it."""

from collections import Counter
from datetime import timedelta

import pytest
from sqlalchemy import event, func, select, text

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


async def audit_rows(session):
    """Every audit row exactly as stored, changes as the database's own text of the JSON."""
    rows = await session.execute(
        text(
            "SELECT id, actor_id, entity_type, entity_id, action, changes::text, created_at "
            "FROM audit_logs ORDER BY id"
        )
    )
    return [tuple(r) for r in rows]


async def test_replaces_whatever_visitors_did_with_a_fresh_demo(session, client, yesterdays_demo):
    await visit(client, session)
    now = sla.utcnow()

    result = await reset_demo(session, settings=DEMO_ON, now=now)

    created = result.created
    assert (created.tickets, created.assets, created.articles) == (
        len(DEMO_TICKETS),
        len(DEMO_ASSETS),
        len(DEMO_ARTICLES),
    )
    assert created.users == 0  # accounts are kept, not recreated
    assert result.removed["tickets"] == len(DEMO_TICKETS) + 1  # with the visitor's
    assert result.removed["assets"] == len(DEMO_ASSETS) + 1
    assert result.removed["articles"] == len(DEMO_ARTICLES) - 1  # a visitor deleted one
    titles = set(await session.scalars(select(Ticket.title)))
    assert titles == {t.title for t in DEMO_TICKETS}
    assert await count(session, Asset) == len(DEMO_ASSETS)
    assert set(await session.scalars(select(Article.title))) == {a.title for a in DEMO_ARTICLES}


async def test_never_changes_the_audit_log_and_records_the_reset_in_it(
    session, client, yesterdays_demo
):
    await visit(client, session)
    before = await audit_rows(session)
    now = sla.utcnow()

    result = await reset_demo(session, settings=DEMO_ON, now=now)

    after = await audit_rows(session)
    assert after[: len(before)] == before  # every earlier row, byte for byte
    added = after[len(before) :]
    assert all(row[0] > before[-1][0] for row in added)  # only appended

    reset_entries = [row for row in added if row[2:5] == ("demo", 0, "reset")]
    assert len(reset_entries) == 1
    entry = await session.get(AuditLog, reset_entries[0][0])
    assert entry.actor_id is None  # the system did it
    assert entry.created_at == now
    assert entry.changes == {
        "ticket_links_removed": result.removed["ticket_links"],
        "comments_removed": result.removed["comments"],
        "tickets_removed": len(DEMO_TICKETS) + 1,
        "assets_removed": len(DEMO_ASSETS) + 1,
        "articles_removed": len(DEMO_ARTICLES) - 1,
        "tickets_created": len(DEMO_TICKETS),
        "assets_created": len(DEMO_ASSETS),
        "articles_created": len(DEMO_ARTICLES),
    }


async def test_sends_no_statement_that_could_change_audit_rows(engine, session, yesterdays_demo):
    statements: list[str] = []

    def remember(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()).lower())

    event.listen(engine.sync_engine, "before_cursor_execute", remember)
    try:
        await reset_demo(session, settings=DEMO_ON)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", remember)

    touching = [s for s in statements if "audit_logs" in s]
    assert touching, "the reset does write its own entries"
    assert all(s.startswith(("insert into audit_logs", "select")) for s in touching), touching
    assert not any(s.startswith(("truncate", "alter sequence")) for s in statements)


async def test_ids_and_asset_tags_are_never_reused(session, yesterdays_demo):
    old_ticket = await session.scalar(select(func.max(Ticket.id)))
    old_asset = await session.scalar(select(func.max(Asset.id)))
    old_article = await session.scalar(select(func.max(Article.id)))
    old_tags = set(await session.scalars(select(Asset.asset_tag)))

    await reset_demo(session, settings=DEMO_ON)

    # So an old audit entry can never come to describe a new, unrelated record.
    assert await session.scalar(select(func.min(Ticket.id))) > old_ticket
    assert await session.scalar(select(func.min(Asset.id))) > old_asset
    assert await session.scalar(select(func.min(Article.id))) > old_article
    new_tags = set(await session.scalars(select(Asset.asset_tag)))
    assert not new_tags & old_tags
    assert min(new_tags) > max(old_tags)


async def test_the_audit_screen_tells_removed_records_from_live_ones(
    session, client, yesterdays_demo
):
    old_ticket = await session.scalar(select(Ticket.id).order_by(Ticket.id))
    await reset_demo(session, settings=DEMO_ON)
    new_ticket = await session.scalar(select(Ticket.id).order_by(Ticket.id))
    headers = await headers_for(client, ADMIN)

    async def entries(**params):
        res = await client.get("/api/audit-logs", params=params, headers=headers)
        assert res.status_code == 200, res.text
        return res.json()["items"]

    old = await entries(entity_type="ticket", entity_id=old_ticket)
    assert old and not any(e["record_exists"] for e in old)
    new = await entries(entity_type="ticket", entity_id=new_ticket)
    assert new and all(e["record_exists"] for e in new)
    (reset_entry,) = await entries(entity_type="demo", action="reset")
    assert reset_entry["actor"] is None
    assert reset_entry["record_exists"] is False  # not a record with a page of its own


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


async def test_resetting_again_gives_the_same_demo_and_appends_the_same_history(
    session, yesterdays_demo
):
    now = sla.utcnow()
    live = (Ticket, TicketComment, Asset, Article)
    audit_before = await count(session, AuditLog)
    await reset_demo(session, settings=DEMO_ON, now=now)
    first = [await count(session, m) for m in live]
    first_added = await count(session, AuditLog) - audit_before

    await reset_demo(session, settings=DEMO_ON, now=now)

    assert [await count(session, m) for m in live] == first
    assert await count(session, AuditLog) - audit_before == 2 * first_added  # it only grows


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

    assert result.created.tickets == len(DEMO_TICKETS)
    assert result.removed["tickets"] == 0


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
