from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Asset, AssetStatus, AssetType

LAPTOP = {
    "type": "laptop",
    "manufacturer": "Dell",
    "model": "Latitude 7440",
    "serial_number": "SN-1001",
    "location": "HQ stockroom",
}


def today():
    return datetime.now(UTC).date()


async def create_asset(client, headers, **overrides):
    res = await client.post("/api/assets", json={**LAPTOP, **overrides}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def assign(client, headers, asset_id, user_id):
    return await client.put(
        f"/api/assets/{asset_id}/assignment", json={"assigned_to_id": user_id}, headers=headers
    )


async def set_status(client, headers, asset_id, status):
    return await client.post(
        f"/api/assets/{asset_id}/status", json={"status": status}, headers=headers
    )


async def test_create_generates_sequential_tags_and_defaults_to_in_stock(client, people):
    _, headers = people["agent"]
    first = await create_asset(client, headers, serial_number="A")
    second = await create_asset(client, headers, serial_number="B")
    assert first["asset_tag"].startswith("DF-")
    assert first["status"] == "in_stock"
    assert first["assigned_to"] is None
    assert int(second["asset_tag"][3:]) == int(first["asset_tag"][3:]) + 1


async def test_explicit_tag_is_normalised_and_must_be_unique(client, people):
    _, headers = people["agent"]
    asset = await create_asset(client, headers, asset_tag=" lt-0042 ", serial_number="A")
    assert asset["asset_tag"] == "LT-0042"
    res = await client.post(
        "/api/assets",
        json={**LAPTOP, "asset_tag": "LT-0042", "serial_number": "B"},
        headers=headers,
    )
    assert res.status_code == 409


async def test_serial_numbers_are_unique_but_optional(client, people):
    _, headers = people["agent"]
    await create_asset(client, headers, serial_number="SN-1")
    duplicate = await client.post(
        "/api/assets", json=LAPTOP | {"serial_number": "SN-1"}, headers=headers
    )
    assert duplicate.status_code == 409
    # Equipment without a serial (a cable, a keyboard) can be added any number of times.
    await create_asset(client, headers, serial_number=None, type="peripheral")
    await create_asset(client, headers, serial_number=None, type="peripheral")
    await create_asset(client, headers, serial_number="", type="peripheral")


@pytest.mark.parametrize(
    "overrides",
    [
        {"type": "toaster"},
        {"manufacturer": "   "},
        {"model": ""},
        {"asset_tag": "bad tag!"},
        {"purchase_date": "2026-05-01", "warranty_expires_on": "2026-01-01"},
    ],
)
async def test_create_validates_input(client, people, overrides):
    _, headers = people["agent"]
    res = await client.post("/api/assets", json={**LAPTOP, **overrides}, headers=headers)
    assert res.status_code == 422


async def test_only_staff_can_create(client, people):
    _, req_headers = people["req"]
    assert (await client.post("/api/assets", json=LAPTOP, headers=req_headers)).status_code == 403
    assert (await client.post("/api/assets", json=LAPTOP)).status_code == 401


async def test_requesters_only_see_equipment_assigned_to_them(client, people):
    req, req_headers = people["req"]
    other, _ = people["other"]
    _, agent_headers = people["agent"]
    mine = await create_asset(client, agent_headers, serial_number="A")
    theirs = await create_asset(client, agent_headers, serial_number="B")
    spare = await create_asset(client, agent_headers, serial_number="C")
    await assign(client, agent_headers, mine["id"], req.id)
    await assign(client, agent_headers, theirs["id"], other.id)

    listing = (await client.get("/api/assets", headers=req_headers)).json()
    assert [a["id"] for a in listing["items"]] == [mine["id"]]
    assert (await client.get(f"/api/assets/{mine['id']}", headers=req_headers)).status_code == 200
    # Someone else's, and unassigned stock, look the same as a missing asset.
    for hidden in (theirs, spare):
        res = await client.get(f"/api/assets/{hidden['id']}", headers=req_headers)
        assert res.status_code == 404

    assert (await client.get("/api/assets", headers=agent_headers)).json()["total"] == 3


async def test_staff_list_filters_search_and_pagination(client, people):
    _, headers = people["agent"]
    await create_asset(client, headers, asset_tag="A-1", manufacturer="Dell", serial_number="S1")
    await create_asset(
        client,
        headers,
        asset_tag="A-2",
        type="monitor",
        manufacturer="LG",
        model="27UK",
        serial_number="S2",
        location="Room 4",
    )
    await create_asset(
        client, headers, asset_tag="A-3", type="monitor", manufacturer="LG", serial_number="S3"
    )

    everything = (await client.get("/api/assets", headers=headers)).json()
    assert [a["asset_tag"] for a in everything["items"]] == ["A-1", "A-2", "A-3"]

    monitors = (await client.get("/api/assets?type=monitor", headers=headers)).json()
    assert monitors["total"] == 2
    for query, tag in (("27uk", "A-2"), ("room 4", "A-2"), ("s1", "A-1"), ("a-3", "A-3")):
        found = (await client.get(f"/api/assets?q={query}", headers=headers)).json()
        assert [a["asset_tag"] for a in found["items"]] == [tag], query

    page = (await client.get("/api/assets?limit=2&offset=2", headers=headers)).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1


async def test_warranty_state_and_filters(client, people):
    _, headers = people["agent"]
    soon = (today() + timedelta(days=10)).isoformat()
    later = (today() + timedelta(days=400)).isoformat()
    past = (today() - timedelta(days=5)).isoformat()
    expiring = await create_asset(client, headers, serial_number="1", warranty_expires_on=soon)
    active = await create_asset(client, headers, serial_number="2", warranty_expires_on=later)
    expired = await create_asset(client, headers, serial_number="3", warranty_expires_on=past)
    none = await create_asset(client, headers, serial_number="4")
    assert [a["warranty_state"] for a in (expiring, active, expired, none)] == [
        "expiring",
        "active",
        "expired",
        None,
    ]

    def ids(res):
        return [a["id"] for a in res.json()["items"]]

    assert ids(await client.get("/api/assets?warranty=expiring", headers=headers)) == [
        expiring["id"]
    ]
    assert ids(await client.get("/api/assets?warranty=expired", headers=headers)) == [expired["id"]]

    # Retiring equipment takes it out of warranty reminders.
    await set_status(client, headers, expiring["id"], "retired")
    assert ids(await client.get("/api/assets?warranty=expiring", headers=headers)) == []


async def test_update_changes_fields_and_clears_optional_ones(client, people):
    _, headers = people["agent"]
    asset = await create_asset(client, headers)
    res = await client.patch(
        f"/api/assets/{asset['id']}",
        json={"model": "Latitude 7450", "location": None, "notes": "New battery fitted"},
        headers=headers,
    )
    body = res.json()
    assert body["model"] == "Latitude 7450"
    assert body["location"] is None
    assert body["notes"] == "New battery fitted"
    assert body["manufacturer"] == "Dell"  # untouched


async def test_update_rejects_nulling_required_fields_and_duplicate_serials(client, people):
    _, headers = people["agent"]
    first = await create_asset(client, headers, serial_number="SN-A")
    second = await create_asset(client, headers, serial_number="SN-B")
    url = f"/api/assets/{second['id']}"
    assert (await client.patch(url, json={"model": None}, headers=headers)).status_code == 422
    assert (
        await client.patch(url, json={"serial_number": "SN-A"}, headers=headers)
    ).status_code == 409
    # Re-saving its own serial is fine.
    assert (
        await client.patch(url, json={"serial_number": "SN-B"}, headers=headers)
    ).status_code == 200
    assert first["id"] != second["id"]


async def test_requester_cannot_update(client, people):
    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    asset = await create_asset(client, agent_headers)
    await assign(client, agent_headers, asset["id"], req.id)
    res = await client.patch(f"/api/assets/{asset['id']}", json={"model": "x"}, headers=req_headers)
    assert res.status_code == 403


async def test_assign_unassign_and_reassign(client, people):
    req, _ = people["req"]
    other, _ = people["other"]
    _, headers = people["agent"]
    asset_id = (await create_asset(client, headers))["id"]

    assigned = (await assign(client, headers, asset_id, req.id)).json()
    assert assigned["status"] == "assigned"
    assert assigned["assigned_to"]["id"] == req.id

    moved = (await assign(client, headers, asset_id, other.id)).json()
    assert moved["assigned_to"]["id"] == other.id
    assert moved["status"] == "assigned"

    returned = (await assign(client, headers, asset_id, None)).json()
    assert returned["status"] == "in_stock"
    assert returned["assigned_to"] is None


async def test_assignment_rules(client, people):
    req, req_headers = people["req"]
    _, headers = people["agent"]
    asset_id = (await create_asset(client, headers))["id"]

    assert (
        await assign(client, headers, asset_id, None)
    ).status_code == 409  # nothing to take back
    assert (await assign(client, headers, 99999, req.id)).status_code == 404
    assert (await assign(client, headers, asset_id, 99999)).status_code == 422
    assert (await assign(client, req_headers, asset_id, req.id)).status_code == 403

    for blocked in ("in_repair", "retired"):
        target = (await create_asset(client, headers, serial_number=blocked))["id"]
        await set_status(client, headers, target, blocked)
        assert (await assign(client, headers, target, req.id)).status_code == 409


async def test_cannot_assign_to_an_inactive_user(client, session, people):
    req, _ = people["req"]
    _, headers = people["agent"]
    asset_id = (await create_asset(client, headers))["id"]
    req.is_active = False
    await session.flush()
    assert (await assign(client, headers, asset_id, req.id)).status_code == 422


@pytest.mark.parametrize(
    ("start", "target", "allowed"),
    [
        ("in_stock", "in_repair", True),
        ("in_stock", "retired", True),
        ("in_repair", "in_stock", True),
        ("in_repair", "retired", True),
        ("assigned", "in_repair", True),
        ("assigned", "retired", True),
        ("in_stock", "assigned", False),  # only via the assignment endpoint
        ("in_repair", "assigned", False),
        ("assigned", "in_stock", False),  # likewise: unassign instead
        ("retired", "in_stock", False),
        ("retired", "in_repair", False),
    ],
)
async def test_status_transitions(client, people, start, target, allowed):
    req, _ = people["req"]
    _, headers = people["agent"]
    asset_id = (await create_asset(client, headers))["id"]
    if start == "assigned":
        await assign(client, headers, asset_id, req.id)
    elif start != "in_stock":
        await set_status(client, headers, asset_id, start)

    res = await set_status(client, headers, asset_id, target)
    assert res.status_code == (200 if allowed else 409), res.text


async def test_sending_an_assigned_asset_for_repair_takes_it_back(client, people):
    req, _ = people["req"]
    _, headers = people["agent"]
    asset_id = (await create_asset(client, headers))["id"]
    await assign(client, headers, asset_id, req.id)

    repaired = (await set_status(client, headers, asset_id, "in_repair")).json()
    assert repaired["status"] == "in_repair"
    assert repaired["assigned_to"] is None


async def test_database_refuses_an_assigned_asset_without_an_assignee(session):
    session.add(
        Asset(
            asset_tag="BAD-1",
            type=AssetType.LAPTOP,
            manufacturer="x",
            model="y",
            status=AssetStatus.ASSIGNED,
            assigned_to_id=None,
        )
    )
    with pytest.raises(IntegrityError, match="assignment_matches_status"):
        await session.flush()


async def test_history_records_every_change_with_before_and_after(client, people):
    req, _ = people["req"]
    _, headers = people["agent"]
    asset = await create_asset(client, headers)
    asset_id = asset["id"]
    await client.patch(f"/api/assets/{asset_id}", json={"location": "Floor 2"}, headers=headers)
    await assign(client, headers, asset_id, req.id)
    await set_status(client, headers, asset_id, "in_repair")
    # A no-op edit leaves no trace.
    await client.patch(f"/api/assets/{asset_id}", json={"location": "Floor 2"}, headers=headers)

    entries = (await client.get(f"/api/assets/{asset_id}/history", headers=headers)).json()
    assert [e["action"] for e in entries] == ["created", "updated", "assigned", "status_changed"]
    assert entries[0]["changes"]["asset_tag"] == asset["asset_tag"]
    assert entries[1]["changes"] == {"location": ["HQ stockroom", "Floor 2"]}
    assert entries[2]["changes"] == {
        "status": ["in_stock", "assigned"],
        "assigned_to_id": [None, req.id],
    }
    assert entries[3]["changes"] == {
        "status": ["assigned", "in_repair"],
        "assigned_to_id": [req.id, None],
    }


async def test_history_is_staff_only_and_visible_to_admin_audit_log(client, people):
    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    _, admin_headers = people["admin"]
    asset_id = (await create_asset(client, agent_headers))["id"]
    await assign(client, agent_headers, asset_id, req.id)

    assert (
        await client.get(f"/api/assets/{asset_id}/history", headers=req_headers)
    ).status_code == 403
    log = (
        await client.get(
            f"/api/audit-logs?entity_type=asset&entity_id={asset_id}", headers=admin_headers
        )
    ).json()
    assert log["total"] == 2


async def test_audit_dates_are_serialised(client, people):
    _, headers = people["agent"]
    asset = await create_asset(
        client, headers, purchase_date="2026-01-15", warranty_expires_on="2029-01-15"
    )
    entries = (await client.get(f"/api/assets/{asset['id']}/history", headers=headers)).json()
    assert entries[0]["changes"]["purchase_date"] == "2026-01-15"
    assert entries[0]["changes"]["warranty_expires_on"] == "2029-01-15"


async def test_assets_require_authentication(client):
    assert (await client.get("/api/assets")).status_code == 401
