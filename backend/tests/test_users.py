import pytest

from app.models import Role

NEW_USER = {"email": "New@Example.com", "full_name": "New Person", "password": "longenough"}


async def test_admin_can_create_user(client, make_user, auth_headers):
    admin = await make_user(Role.ADMIN)
    res = await client.post("/api/users", json=NEW_USER, headers=await auth_headers(admin))
    assert res.status_code == 201
    assert res.json()["email"] == "new@example.com"
    assert res.json()["role"] == "requester"


async def test_duplicate_email_conflicts(client, make_user, auth_headers):
    admin = await make_user(Role.ADMIN)
    headers = await auth_headers(admin)
    await client.post("/api/users", json=NEW_USER, headers=headers)
    res = await client.post("/api/users", json=NEW_USER, headers=headers)
    assert res.status_code == 409


@pytest.mark.parametrize("role", [Role.REQUESTER, Role.AGENT])
async def test_non_admin_cannot_create_user(client, make_user, auth_headers, role):
    user = await make_user(role)
    res = await client.post("/api/users", json=NEW_USER, headers=await auth_headers(user))
    assert res.status_code == 403


async def test_requester_cannot_list_users(client, make_user, auth_headers):
    user = await make_user(Role.REQUESTER)
    res = await client.get("/api/users", headers=await auth_headers(user))
    assert res.status_code == 403


async def test_agent_can_list_users(client, make_user, auth_headers):
    agent = await make_user(Role.AGENT)
    res = await client.get("/api/users", headers=await auth_headers(agent))
    assert res.status_code == 200
    assert [u["email"] for u in res.json()] == [agent.email]
