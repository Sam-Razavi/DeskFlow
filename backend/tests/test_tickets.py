NEW_TICKET = {
    "title": "Laptop will not boot",
    "description": "Black screen after the Windows logo.",
    "priority": "p2",
    "category": "hardware",
}


async def create(client, headers, **overrides):
    res = await client.post("/api/tickets", json={**NEW_TICKET, **overrides}, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


async def test_requester_creates_ticket_for_self(client, people):
    user, headers = people["req"]
    ticket = await create(client, headers)
    assert ticket["status"] == "new"
    assert ticket["requester"]["id"] == user.id
    assert ticket["assignee"] is None


async def test_requester_cannot_create_on_behalf_of_someone_else(client, people):
    user, headers = people["req"]
    other, _ = people["other"]
    ticket = await create(client, headers, requester_id=other.id)
    assert ticket["requester"]["id"] == user.id


async def test_staff_can_create_on_behalf_of_requester(client, people):
    req, _ = people["req"]
    _, agent_headers = people["agent"]
    ticket = await create(client, agent_headers, requester_id=req.id)
    assert ticket["requester"]["id"] == req.id


async def test_create_validates_input(client, people):
    _, headers = people["req"]
    res = await client.post("/api/tickets", json={**NEW_TICKET, "title": "x"}, headers=headers)
    assert res.status_code == 422


async def test_requesters_only_see_their_own_tickets(client, people):
    _, req_headers = people["req"]
    _, other_headers = people["other"]
    mine = await create(client, req_headers)
    await create(client, other_headers, title="Someone else's problem")

    listing = (await client.get("/api/tickets", headers=req_headers)).json()
    assert [t["id"] for t in listing["items"]] == [mine["id"]]
    assert listing["total"] == 1


async def test_requester_gets_404_for_foreign_ticket(client, people):
    _, req_headers = people["req"]
    _, other_headers = people["other"]
    ticket = await create(client, req_headers)
    res = await client.get(f"/api/tickets/{ticket['id']}", headers=other_headers)
    assert res.status_code == 404


async def test_staff_see_all_tickets(client, people):
    _, req_headers = people["req"]
    _, other_headers = people["other"]
    _, agent_headers = people["agent"]
    await create(client, req_headers)
    await create(client, other_headers)
    listing = (await client.get("/api/tickets", headers=agent_headers)).json()
    assert listing["total"] == 2


async def test_list_filters_search_and_priority_ordering(client, people):
    _, agent_headers = people["agent"]
    await create(client, agent_headers, title="Printer jam", priority="p4", category="hardware")
    await create(client, agent_headers, title="VPN down", priority="p1", category="network")
    await create(client, agent_headers, title="Excel crashes", priority="p3", category="software")

    all_items = (await client.get("/api/tickets", headers=agent_headers)).json()["items"]
    assert [t["priority"] for t in all_items] == ["p1", "p3", "p4"]

    by_category = (await client.get("/api/tickets?category=network", headers=agent_headers)).json()
    assert [t["title"] for t in by_category["items"]] == ["VPN down"]

    by_search = (await client.get("/api/tickets?q=printer", headers=agent_headers)).json()
    assert [t["title"] for t in by_search["items"]] == ["Printer jam"]


async def test_list_pagination(client, people):
    _, agent_headers = people["agent"]
    for i in range(3):
        await create(client, agent_headers, title=f"Ticket number {i}")
    page = (await client.get("/api/tickets?limit=2&offset=2", headers=agent_headers)).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1


async def test_requester_can_edit_own_new_ticket_but_not_priority(client, people):
    _, headers = people["req"]
    ticket = await create(client, headers)
    ok = await client.patch(
        f"/api/tickets/{ticket['id']}", json={"title": "Laptop dead"}, headers=headers
    )
    assert ok.status_code == 200
    assert ok.json()["title"] == "Laptop dead"

    denied = await client.patch(
        f"/api/tickets/{ticket['id']}", json={"priority": "p1"}, headers=headers
    )
    assert denied.status_code == 403


async def test_requester_cannot_edit_once_work_started(client, people):
    _, req_headers = people["req"]
    agent, agent_headers = people["agent"]
    ticket = await create(client, req_headers)
    await client.put(
        f"/api/tickets/{ticket['id']}/assignee",
        json={"assignee_id": agent.id},
        headers=agent_headers,
    )
    res = await client.patch(
        f"/api/tickets/{ticket['id']}", json={"title": "Changed my mind"}, headers=req_headers
    )
    assert res.status_code == 403


async def test_staff_can_change_priority(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket = await create(client, req_headers)
    res = await client.patch(
        f"/api/tickets/{ticket['id']}", json={"priority": "p1"}, headers=agent_headers
    )
    assert res.json()["priority"] == "p1"


async def test_assigning_moves_new_ticket_to_in_progress(client, people):
    _, req_headers = people["req"]
    agent, agent_headers = people["agent"]
    ticket = await create(client, req_headers)
    res = await client.put(
        f"/api/tickets/{ticket['id']}/assignee",
        json={"assignee_id": agent.id},
        headers=agent_headers,
    )
    assert res.status_code == 200
    assert res.json()["assignee"]["id"] == agent.id
    assert res.json()["status"] == "in_progress"


async def test_cannot_assign_to_requester(client, people):
    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket = await create(client, req_headers)
    res = await client.put(
        f"/api/tickets/{ticket['id']}/assignee", json={"assignee_id": req.id}, headers=agent_headers
    )
    assert res.status_code == 422


async def test_requester_cannot_assign(client, people):
    req, req_headers = people["req"]
    ticket = await create(client, req_headers)
    res = await client.put(
        f"/api/tickets/{ticket['id']}/assignee", json={"assignee_id": req.id}, headers=req_headers
    )
    assert res.status_code == 403


async def test_unassign(client, people):
    _, req_headers = people["req"]
    agent, agent_headers = people["agent"]
    ticket = await create(client, req_headers)
    url = f"/api/tickets/{ticket['id']}/assignee"
    await client.put(url, json={"assignee_id": agent.id}, headers=agent_headers)
    res = await client.put(url, json={"assignee_id": None}, headers=agent_headers)
    assert res.json()["assignee"] is None


async def set_status(client, ticket_id, headers, status):
    return await client.post(
        f"/api/tickets/{ticket_id}/status", json={"status": status}, headers=headers
    )


async def test_status_workflow_and_resolved_timestamp(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]

    res = await set_status(client, tid, agent_headers, "in_progress")
    assert res.json()["status"] == "in_progress"
    assert res.json()["resolved_at"] is None

    res = await set_status(client, tid, agent_headers, "resolved")
    assert res.json()["resolved_at"] is not None

    # Reopening clears the resolution timestamp.
    res = await set_status(client, tid, agent_headers, "in_progress")
    assert res.json()["resolved_at"] is None


async def test_invalid_transition_is_rejected(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    await set_status(client, tid, agent_headers, "closed")
    # Closed is terminal.
    res = await set_status(client, tid, agent_headers, "in_progress")
    assert res.status_code == 409


async def test_requester_can_only_confirm_or_reopen_resolved_ticket(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]

    assert (await set_status(client, tid, req_headers, "in_progress")).status_code == 409
    await set_status(client, tid, agent_headers, "resolved")
    assert (await set_status(client, tid, req_headers, "pending")).status_code == 409
    res = await set_status(client, tid, req_headers, "closed")
    assert res.status_code == 200
    assert res.json()["status"] == "closed"


async def test_comments_and_internal_notes_visibility(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    url = f"/api/tickets/{tid}/comments"

    await client.post(url, json={"body": "Any update?"}, headers=req_headers)
    await client.post(url, json={"body": "Checking the disk"}, headers=agent_headers)
    await client.post(
        url,
        json={"body": "Probably the SSD, order a spare", "is_internal": True},
        headers=agent_headers,
    )

    as_requester = (await client.get(url, headers=req_headers)).json()
    assert [c["body"] for c in as_requester] == ["Any update?", "Checking the disk"]

    as_agent = (await client.get(url, headers=agent_headers)).json()
    assert len(as_agent) == 3
    assert as_agent[2]["is_internal"] is True


async def test_requester_cannot_post_internal_note(client, people):
    _, req_headers = people["req"]
    tid = (await create(client, req_headers))["id"]
    res = await client.post(
        f"/api/tickets/{tid}/comments",
        json={"body": "secret", "is_internal": True},
        headers=req_headers,
    )
    assert res.status_code == 403


async def test_cannot_comment_on_closed_ticket(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    tid = (await create(client, req_headers))["id"]
    await set_status(client, tid, agent_headers, "closed")
    res = await client.post(
        f"/api/tickets/{tid}/comments", json={"body": "hello?"}, headers=req_headers
    )
    assert res.status_code == 409


async def test_other_requester_cannot_comment(client, people):
    _, req_headers = people["req"]
    _, other_headers = people["other"]
    tid = (await create(client, req_headers))["id"]
    res = await client.post(
        f"/api/tickets/{tid}/comments", json={"body": "hi"}, headers=other_headers
    )
    assert res.status_code == 404


async def test_requires_authentication(client):
    assert (await client.get("/api/tickets")).status_code == 401
    assert (await client.post("/api/tickets", json=NEW_TICKET)).status_code == 401
