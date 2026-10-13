import csv
import io
import json
from datetime import UTC, datetime

import pytest

from app.api.routes import audit as audit_routes
from app.models import AuditLog
from tests.test_articles import create as create_article
from tests.test_assets import create_asset
from tests.test_tickets import create as create_ticket
from tests.test_tickets import set_status


def at(day: int, hour: int = 12, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, second, tzinfo=UTC)


@pytest.fixture
async def history(session, people):
    """Rows with known timestamps so date filtering can be tested exactly."""
    agent, _ = people["agent"]
    admin, _ = people["admin"]
    rows = [
        AuditLog(
            actor_id=agent.id,
            entity_type="ticket",
            entity_id=1,
            action="created",
            changes={},
            created_at=at(1),
        ),
        AuditLog(
            actor_id=agent.id,
            entity_type="ticket",
            entity_id=1,
            action="status_changed",
            changes={"status": ["new", "resolved"]},
            created_at=at(2, 0, 0, 0),
        ),
        AuditLog(
            actor_id=admin.id,
            entity_type="asset",
            entity_id=7,
            action="assigned",
            changes={"assigned_to_id": [None, 3]},
            created_at=at(2, 23, 59, 59),
        ),
        AuditLog(
            actor_id=None,
            entity_type="ticket",
            entity_id=1,
            action="sla_breached",
            changes={"kind": "resolution"},
            created_at=at(3, 0, 0, 0),
        ),
        AuditLog(
            actor_id=agent.id,
            entity_type="article",
            entity_id=4,
            action="published",
            changes={},
            created_at=at(5),
        ),
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def get(client, headers, path="/api/audit-logs", **params):
    res = await client.get(path, params=params, headers=headers)
    assert res.status_code == 200, res.text
    return res


def actions(page):
    return [e["action"] for e in page.json()["items"]]


async def test_only_admins_can_use_any_of_it(client, people):
    for path in ("/api/audit-logs", "/api/audit-logs/facets", "/api/audit-logs/export.csv"):
        for who in ("req", "agent"):
            _, headers = people[who]
            assert (await client.get(path, headers=headers)).status_code == 403, (path, who)
        assert (await client.get(path)).status_code == 401, path


async def test_lists_newest_first(client, people, history):
    _, admin = people["admin"]
    page = (await get(client, admin)).json()
    assert page["total"] == 5
    assert [e["action"] for e in page["items"]] == [
        "published",
        "sla_breached",
        "assigned",
        "status_changed",
        "created",
    ]


async def test_filters_by_action(client, people, history):
    _, admin = people["admin"]
    assert actions(await get(client, admin, action="created")) == ["created"]
    assert (await get(client, admin, action="nonexistent")).json()["total"] == 0


async def test_filters_by_actor_and_record(client, people, history):
    agent, _ = people["agent"]
    _, admin = people["admin"]
    by_agent = await get(client, admin, actor_id=agent.id)
    assert by_agent.json()["total"] == 3
    one_record = await get(client, admin, entity_type="ticket", entity_id=1)
    assert one_record.json()["total"] == 3
    system = [e for e in one_record.json()["items"] if e["actor"] is None]
    assert [e["action"] for e in system] == ["sla_breached"]


async def test_filters_combine(client, people, history):
    agent, _ = people["agent"]
    _, admin = people["admin"]
    page = await get(
        client, admin, actor_id=agent.id, entity_type="ticket", action="status_changed"
    )
    assert actions(page) == ["status_changed"]


async def test_date_range_is_whole_days_and_inclusive_at_both_ends(client, people, history):
    _, admin = people["admin"]
    # Sep 2 has rows at 00:00:00 and 23:59:59: both are in, and Sep 1 / Sep 3 rows are out.
    day = await get(client, admin, **{"from": "2026-09-02", "to": "2026-09-02"})
    assert actions(day) == ["assigned", "status_changed"]
    # Opening bound only, closing bound only.
    assert (await get(client, admin, **{"from": "2026-09-03"})).json()["total"] == 2
    assert (await get(client, admin, to="2026-09-01")).json()["total"] == 1


async def test_a_backwards_range_is_simply_empty_and_bad_dates_are_rejected(
    client, people, history
):
    _, admin = people["admin"]
    assert (await get(client, admin, **{"from": "2026-09-05", "to": "2026-09-01"})).json()[
        "total"
    ] == 0
    for bad in ("yesterday", "2026-13-40", "09/02/2026"):
        res = await client.get("/api/audit-logs", params={"from": bad}, headers=admin)
        assert res.status_code == 422, bad


async def test_pagination_keeps_the_total(client, people, history):
    _, admin = people["admin"]
    page = (await get(client, admin, limit=2, offset=2)).json()
    assert page["total"] == 5
    assert [e["action"] for e in page["items"]] == ["assigned", "status_changed"]


async def test_facets_list_what_is_in_the_log(client, people, history):
    _, admin = people["admin"]
    facets = (await get(client, admin, "/api/audit-logs/facets")).json()
    assert facets["entity_types"] == ["article", "asset", "ticket"]
    assert facets["actions"] == [
        "assigned",
        "created",
        "published",
        "sla_breached",
        "status_changed",
    ]


async def test_real_activity_across_every_module_shows_up_together(client, people):
    _, agent = people["agent"]
    _, req = people["req"]
    _, admin = people["admin"]
    ticket = await create_ticket(client, req)
    await set_status(client, ticket["id"], agent, "in_progress")
    await create_asset(client, agent)
    await create_article(client, agent, publish=True)

    facets = (await get(client, admin, "/api/audit-logs/facets")).json()
    assert {"ticket", "asset", "article"} <= set(facets["entity_types"])
    assert {"created", "status_changed", "published"} <= set(facets["actions"])


# --- export --------------------------------------------------------------------------------------


def parse(response):
    return list(csv.reader(io.StringIO(response.text)))


async def test_export_is_a_downloadable_csv_with_a_header_row(client, people, history):
    _, admin = people["admin"]
    res = await get(client, admin, "/api/audit-logs/export.csv")
    assert res.headers["content-type"].startswith("text/csv")
    assert res.headers["content-disposition"].startswith('attachment; filename="audit-log-')
    rows = parse(res)
    assert rows[0] == [
        "id",
        "time_utc",
        "actor_id",
        "actor",
        "record_type",
        "record_id",
        "action",
        "changes",
    ]
    assert len(rows) == 6  # header + 5 entries
    assert [r[6] for r in rows[1:]] == [
        "published",
        "sla_breached",
        "assigned",
        "status_changed",
        "created",
    ]


async def test_export_describes_each_entry_fully(client, people, history):
    _, admin = people["admin"]
    rows = parse(await get(client, admin, "/api/audit-logs/export.csv", action="assigned"))
    _, time_utc, _, actor, record_type, record_id, action, changes = rows[1]
    assert time_utc == "2026-09-02T23:59:59+00:00"
    assert (actor, record_type, record_id, action) == ("Test Admin", "asset", "7", "assigned")
    assert json.loads(changes) == {"assigned_to_id": [None, 3]}


async def test_export_names_system_events_and_honours_the_filters(client, people, history):
    _, admin = people["admin"]
    rows = parse(
        await get(
            client,
            admin,
            "/api/audit-logs/export.csv",
            **{"from": "2026-09-03", "to": "2026-09-03"},
        )
    )
    assert len(rows) == 2
    assert rows[1][3] == "System"
    assert rows[1][2] == ""  # no actor id


async def test_export_neutralises_spreadsheet_formulas_in_any_cell(client, session, people):
    agent, _ = people["agent"]
    _, admin = people["admin"]
    agent.full_name = '=HYPERLINK("http://evil.example","click")'
    session.add(
        AuditLog(actor_id=agent.id, entity_type="ticket", entity_id=1, action="@SUM(1)", changes={})
    )
    await session.flush()

    rows = parse(await get(client, admin, "/api/audit-logs/export.csv"))
    actor, action = rows[1][3], rows[1][6]
    assert actor.startswith("'=") and action.startswith("'@")
    assert not any(cell.startswith(("=", "+", "@")) for row in rows for cell in row)


async def test_export_is_capped(client, people, history, monkeypatch):
    _, admin = people["admin"]
    monkeypatch.setattr(audit_routes, "EXPORT_LIMIT", 3)
    rows = parse(await get(client, admin, "/api/audit-logs/export.csv"))
    assert len(rows) == 4  # header + the 3 newest
    assert rows[1][6] == "published"


async def test_an_empty_export_is_just_the_header(client, people):
    _, admin = people["admin"]
    rows = parse(await get(client, admin, "/api/audit-logs/export.csv", action="nothing"))
    assert len(rows) == 1
