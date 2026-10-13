from tests.test_tickets import create, people, set_status  # noqa: F401


async def history(client, headers, ticket_id):
    res = await client.get(f"/api/tickets/{ticket_id}/history", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def test_every_ticket_change_is_audited_in_order(client, people):  # noqa: F811
    req, req_headers = people["req"]
    agent, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]

    await client.patch(f"/api/tickets/{tid}", json={"priority": "p1"}, headers=agent_headers)
    await client.put(
        f"/api/tickets/{tid}/assignee", json={"assignee_id": agent.id}, headers=agent_headers
    )
    await set_status(client, tid, agent_headers, "resolved")
    await client.post(f"/api/tickets/{tid}/comments", json={"body": "Fixed"}, headers=agent_headers)

    entries = await history(client, agent_headers, tid)
    assert [e["action"] for e in entries] == [
        "created",
        "updated",
        "assigned",
        "status_changed",
        "commented",
    ]
    assert entries[0]["actor"]["id"] == req.id
    assert entries[1]["actor"]["id"] == agent.id


async def test_audit_records_before_and_after_values(client, people):  # noqa: F811
    _, req_headers = people["req"]
    agent, agent_headers = people["agent"]
    tid = (await create(client, req_headers, priority="p3"))["id"]

    await client.patch(f"/api/tickets/{tid}", json={"priority": "p1"}, headers=agent_headers)
    await client.put(
        f"/api/tickets/{tid}/assignee", json={"assignee_id": agent.id}, headers=agent_headers
    )

    entries = await history(client, agent_headers, tid)
    assert entries[1]["changes"] == {"priority": ["p3", "p1"]}
    # Assigning an untouched ticket also moves it to in_progress, and both changes are captured.
    assert entries[2]["changes"] == {
        "assignee_id": [None, agent.id],
        "status": ["new", "in_progress"],
    }


async def test_no_audit_row_for_a_noop_update(client, people):  # noqa: F811
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket = await create(client, req_headers)
    await client.patch(
        f"/api/tickets/{ticket['id']}", json={"title": ticket["title"]}, headers=agent_headers
    )
    entries = await history(client, agent_headers, ticket["id"])
    assert [e["action"] for e in entries] == ["created"]


async def test_failed_request_leaves_no_audit_row(client, people):  # noqa: F811
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    await set_status(client, tid, agent_headers, "closed")
    await set_status(client, tid, agent_headers, "in_progress")  # rejected: closed is terminal
    entries = await history(client, agent_headers, tid)
    assert [e["action"] for e in entries] == ["created", "status_changed"]


async def test_requester_cannot_read_history(client, people):  # noqa: F811
    _, req_headers = people["req"]
    tid = (await create(client, req_headers))["id"]
    res = await client.get(f"/api/tickets/{tid}/history", headers=req_headers)
    assert res.status_code == 403


async def test_audit_log_endpoint_is_admin_only_and_filterable(client, people):  # noqa: F811
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    _, admin_headers = people["admin"]
    first = (await create(client, req_headers))["id"]
    await create(client, req_headers)

    assert (await client.get("/api/audit-logs", headers=agent_headers)).status_code == 403
    assert (await client.get("/api/audit-logs", headers=req_headers)).status_code == 403

    everything = (await client.get("/api/audit-logs", headers=admin_headers)).json()
    assert everything["total"] == 2
    # Newest first.
    assert everything["items"][0]["entity_id"] > everything["items"][1]["entity_id"]

    one = (
        await client.get(
            f"/api/audit-logs?entity_type=ticket&entity_id={first}", headers=admin_headers
        )
    ).json()
    assert one["total"] == 1
