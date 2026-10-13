from app.models import Role
from tests.conftest import PASSWORD


async def test_health(client):
    res = await client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


async def test_login_and_me(client, make_user, auth_headers):
    user = await make_user(Role.AGENT)
    res = await client.get("/api/auth/me", headers=await auth_headers(user))
    assert res.status_code == 200
    assert res.json()["email"] == user.email
    assert res.json()["role"] == "agent"


async def test_login_is_case_insensitive_on_email(client, make_user):
    user = await make_user()
    res = await client.post(
        "/api/auth/login", data={"username": user.email.upper(), "password": PASSWORD}
    )
    assert res.status_code == 200


async def test_login_wrong_password(client, make_user):
    user = await make_user()
    res = await client.post("/api/auth/login", data={"username": user.email, "password": "nope"})
    assert res.status_code == 401


async def test_me_requires_token(client):
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_refresh_issues_new_tokens(client, make_user):
    user = await make_user()
    tokens = (
        await client.post("/api/auth/login", data={"username": user.email, "password": PASSWORD})
    ).json()
    res = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert res.status_code == 200
    assert "access_token" in res.json()


async def test_access_token_cannot_be_used_as_refresh(client, make_user):
    user = await make_user()
    tokens = (
        await client.post("/api/auth/login", data={"username": user.email, "password": PASSWORD})
    ).json()
    res = await client.post("/api/auth/refresh", json={"refresh_token": tokens["access_token"]})
    assert res.status_code == 401


async def test_inactive_user_cannot_login(client, session, make_user):
    user = await make_user()
    user.is_active = False
    await session.flush()
    res = await client.post("/api/auth/login", data={"username": user.email, "password": PASSWORD})
    assert res.status_code == 401
