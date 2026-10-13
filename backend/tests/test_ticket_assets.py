from tests.test_assets import assign, create_asset
from tests.test_tickets import create, set_status


async def link(client, headers, ticket_id, asset_id):
    return await client.put(f"/api/tickets/{ticket_id}/assets/{asset_id}", headers=headers)


async def linked(client, headers, ticket_id):
    res = await client.get(f"/api/tickets/{ticket_id}/assets", headers=headers)
    assert res.status_code == 200, res.text
    return [a["id"] for a in res.json()]


async def history_actions(client, headers, entity, entity_id):
    res = await client.get(f"/api/{entity}/{entity_id}/history", headers=headers)
    return [e["action"] for e in res.json()]


async def test_staff_can_link_and_unlink_any_asset(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    asset_id = (await create_asset(client, agent_headers))["id"]

    res = await link(client, agent_headers, ticket_id, asset_id)
    assert res.status_code == 200
    assert res.json()["id"] == asset_id
    assert await linked(client, agent_headers, ticket_id) == [asset_id]

    res = await client.delete(f"/api/tickets/{ticket_id}/assets/{asset_id}", headers=agent_headers)
    assert res.status_code == 204
    assert await linked(client, agent_headers, ticket_id) == []


async def test_linking_twice_is_harmless_and_audited_once(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    asset_id = (await create_asset(client, agent_headers))["id"]

    await link(client, agent_headers, ticket_id, asset_id)
    assert (await link(client, agent_headers, ticket_id, asset_id)).status_code == 200
    assert await linked(client, agent_headers, ticket_id) == [asset_id]

    ticket_log = await history_actions(client, agent_headers, "tickets", ticket_id)
    assert ticket_log.count("asset_linked") == 1


async def test_link_and_unlink_are_audited_on_both_the_ticket_and_the_asset(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    asset = await create_asset(client, agent_headers)

    await link(client, agent_headers, ticket_id, asset["id"])
    await client.delete(f"/api/tickets/{ticket_id}/assets/{asset['id']}", headers=agent_headers)
    # Unlinking something that is not linked changes nothing and is not logged.
    await client.delete(f"/api/tickets/{ticket_id}/assets/{asset['id']}", headers=agent_headers)

    ticket_entries = (
        await client.get(f"/api/tickets/{ticket_id}/history", headers=agent_headers)
    ).json()
    assert [e["action"] for e in ticket_entries] == ["created", "asset_linked", "asset_unlinked"]
    assert ticket_entries[1]["changes"] == {
        "asset_id": asset["id"],
        "asset_tag": asset["asset_tag"],
    }
    assert await history_actions(client, agent_headers, "assets", asset["id"]) == [
        "created",
        "ticket_linked",
        "ticket_unlinked",
    ]


async def test_requester_can_link_their_own_equipment_to_their_own_ticket(client, people):
    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    asset_id = (await create_asset(client, agent_headers))["id"]
    await assign(client, agent_headers, asset_id, req.id)

    assert (await link(client, req_headers, ticket_id, asset_id)).status_code == 200
    assert await linked(client, req_headers, ticket_id) == [asset_id]
    assert (
        await client.delete(f"/api/tickets/{ticket_id}/assets/{asset_id}", headers=req_headers)
    ).status_code == 204


async def test_requester_cannot_link_equipment_that_is_not_theirs(client, people):
    req, req_headers = people["req"]
    other, _ = people["other"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    theirs = (await create_asset(client, agent_headers, serial_number="A"))["id"]
    spare = (await create_asset(client, agent_headers, serial_number="B"))["id"]
    await assign(client, agent_headers, theirs, other.id)

    assert (await link(client, req_headers, ticket_id, theirs)).status_code == 404
    assert (await link(client, req_headers, ticket_id, spare)).status_code == 404
    assert req.id != other.id


async def test_requester_cannot_touch_someone_elses_ticket(client, people):
    _, req_headers = people["req"]
    other, other_headers = people["other"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    asset_id = (await create_asset(client, agent_headers))["id"]
    await assign(client, agent_headers, asset_id, other.id)

    assert (await link(client, other_headers, ticket_id, asset_id)).status_code == 404
    assert (
        await client.get(f"/api/tickets/{ticket_id}/assets", headers=other_headers)
    ).status_code == 404


async def test_requesters_only_see_their_own_equipment_among_a_tickets_links(client, people):
    req, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    mine = (await create_asset(client, agent_headers, serial_number="A"))["id"]
    stock = (await create_asset(client, agent_headers, serial_number="B"))["id"]
    await assign(client, agent_headers, mine, req.id)
    await link(client, agent_headers, ticket_id, mine)
    await link(client, agent_headers, ticket_id, stock)

    assert sorted(await linked(client, agent_headers, ticket_id)) == sorted([mine, stock])
    assert await linked(client, req_headers, ticket_id) == [mine]


async def test_closed_tickets_cannot_be_relinked(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    asset_id = (await create_asset(client, agent_headers))["id"]
    await link(client, agent_headers, ticket_id, asset_id)
    await set_status(client, ticket_id, agent_headers, "closed")

    assert (await link(client, agent_headers, ticket_id, asset_id)).status_code == 409
    delete = await client.delete(
        f"/api/tickets/{ticket_id}/assets/{asset_id}", headers=agent_headers
    )
    assert delete.status_code == 409


async def test_unknown_ticket_or_asset_is_a_404(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    ticket_id = (await create(client, req_headers))["id"]
    assert (await link(client, agent_headers, ticket_id, 99999)).status_code == 404
    assert (await link(client, agent_headers, 99999, 1)).status_code == 404


async def test_an_asset_lists_the_tickets_linked_to_it(client, people):
    _, req_headers = people["req"]
    _, agent_headers = people["agent"]
    asset_id = (await create_asset(client, agent_headers))["id"]
    older = (await create(client, req_headers, title="First problem"))["id"]
    newer = (await create(client, req_headers, title="Second problem"))["id"]
    await create(client, req_headers, title="Unrelated")
    await link(client, agent_headers, older, asset_id)
    await link(client, agent_headers, newer, asset_id)

    res = await client.get(f"/api/assets/{asset_id}/tickets", headers=agent_headers)
    assert [t["title"] for t in res.json()] == ["Second problem", "First problem"]
    assert (
        await client.get(f"/api/assets/{asset_id}/tickets", headers=req_headers)
    ).status_code == 403
