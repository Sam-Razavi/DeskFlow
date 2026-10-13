from datetime import datetime, timedelta

from tests.test_tickets import create, set_status


def parse(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def get(client, headers, ticket_id):
    return (await client.get(f"/api/tickets/{ticket_id}", headers=headers)).json()


async def test_new_ticket_gets_deadlines_from_its_priority(client, people):
    _, headers = people["req"]
    ticket = await create(client, headers, priority="p1")
    created = parse(ticket["created_at"])
    assert parse(ticket["response_due_at"]) - created == timedelta(hours=1)
    assert parse(ticket["resolution_due_at"]) - created == timedelta(hours=4)
    assert ticket["response_sla"] == "ok"
    assert ticket["resolution_sla"] == "ok"
    assert ticket["sla_state"] == "ok"
    assert ticket["first_response_at"] is None


async def test_changing_priority_recalculates_deadlines(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket = await create(client, req_headers, priority="p4")
    res = await client.patch(
        f"/api/tickets/{ticket['id']}", json={"priority": "p1"}, headers=agent_headers
    )
    updated = res.json()
    assert parse(updated["resolution_due_at"]) - parse(updated["created_at"]) == timedelta(hours=4)


async def test_first_public_staff_reply_stops_the_response_clock(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    url = f"/api/tickets/{tid}/comments"

    # None of these count as a response: the requester talking, or a private note.
    await client.post(url, json={"body": "Hello?"}, headers=req_headers)
    await client.post(url, json={"body": "note", "is_internal": True}, headers=agent_headers)
    assert (await get(client, agent_headers, tid))["first_response_at"] is None

    await client.post(url, json={"body": "On it"}, headers=agent_headers)
    after_reply = await get(client, agent_headers, tid)
    assert after_reply["first_response_at"] is not None
    assert after_reply["response_sla"] == "met"

    # Later replies never move it.
    await client.post(url, json={"body": "Update"}, headers=agent_headers)
    assert (await get(client, agent_headers, tid))["first_response_at"] == after_reply[
        "first_response_at"
    ]


async def test_staff_replying_on_their_own_ticket_is_not_a_response(client, people):
    agent, agent_headers = people["agent"]
    tid = (await create(client, agent_headers))["id"]
    await client.post(
        f"/api/tickets/{tid}/comments", json={"body": "note to self"}, headers=agent_headers
    )
    assert (await get(client, agent_headers, tid))["first_response_at"] is None


async def test_pending_pauses_the_sla_and_resuming_restarts_it(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    original_due = (await get(client, agent_headers, tid))["resolution_due_at"]

    paused = (await set_status(client, tid, agent_headers, "pending")).json()
    assert paused["sla_paused_at"] is not None
    assert paused["resolution_sla"] == "paused"
    assert paused["sla_state"] == "paused"

    resumed = (await set_status(client, tid, agent_headers, "in_progress")).json()
    assert resumed["sla_paused_at"] is None
    assert resumed["resolution_sla"] == "ok"
    # Deadline only moves forward, by (a tiny amount of) waiting time.
    assert parse(resumed["resolution_due_at"]) >= parse(original_due)


async def test_resolving_marks_resolution_met_and_closing_new_ticket_counts_too(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    first = (await create(client, req_headers))["id"]
    resolved = (await set_status(client, first, agent_headers, "resolved")).json()
    assert resolved["resolution_sla"] == "met"

    second = (await create(client, req_headers))["id"]
    closed = (await set_status(client, second, agent_headers, "closed")).json()
    assert closed["resolved_at"] is not None
    assert closed["resolution_sla"] == "met"
    assert closed["response_sla"] == "n/a"


async def test_reopening_restarts_the_resolution_clock_check(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    await set_status(client, tid, agent_headers, "resolved")
    reopened = (await set_status(client, tid, agent_headers, "in_progress")).json()
    assert reopened["resolved_at"] is None
    assert reopened["resolution_sla"] == "ok"
