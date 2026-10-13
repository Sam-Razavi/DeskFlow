import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.ratelimit import RateLimiter, get_limiter
from app.main import app
from app.models import Role
from tests.conftest import PASSWORD

LOGIN = "/api/auth/login"


async def attempt(client, email, password="wrong-password"):
    return await client.post(LOGIN, data={"username": email, "password": password})


async def fail_times(client, email, times):
    for _ in range(times):
        assert (await attempt(client, email)).status_code == 401


@pytest.fixture
async def user(make_user):
    return await make_user(Role.REQUESTER, "target@example.com")


async def test_five_wrong_passwords_lock_the_sixth_attempt_even_if_it_is_right(client, user):
    await fail_times(client, user.email, 5)
    res = await attempt(client, user.email, PASSWORD)  # the correct password
    assert res.status_code == 429
    assert "Try again in" in res.json()["detail"]
    assert 0 < int(res.headers["retry-after"]) <= get_settings().login_window_seconds


async def test_the_lockout_message_rounds_up_to_whole_minutes(client, user):
    await fail_times(client, user.email, 5)
    res = await attempt(client, user.email)
    assert "15 minutes" in res.json()["detail"]


async def test_a_wrong_guess_does_not_reveal_whether_the_account_exists(client, user):
    # A real account and one that does not exist behave identically all the way to the lockout.
    for email in (user.email, "nobody@example.com"):
        await fail_times(client, email, 5)
        assert (await attempt(client, email)).status_code == 429


async def test_signing_in_successfully_clears_the_failures(client, user):
    await fail_times(client, user.email, 4)
    assert (await attempt(client, user.email, PASSWORD)).status_code == 200
    await fail_times(client, user.email, 4)  # a fresh allowance, so still not locked
    assert (await attempt(client, user.email, PASSWORD)).status_code == 200


async def test_one_persons_lockout_does_not_affect_other_accounts(client, user, make_user):
    other = await make_user(Role.AGENT, "someone-else@example.com")
    await fail_times(client, user.email, 5)
    assert (await attempt(client, user.email, PASSWORD)).status_code == 429
    assert (await attempt(client, other.email, PASSWORD)).status_code == 200


async def test_guessing_from_elsewhere_cannot_lock_the_real_user_out(client, user):
    await fail_times(client, user.email, 5)
    # The same account, from a different address, is not locked: the counter includes the address.
    transport = ASGITransport(app=app, client=("203.0.113.50", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as elsewhere:
        assert (await attempt(elsewhere, user.email, PASSWORD)).status_code == 200


async def test_one_address_cannot_spray_guesses_across_many_accounts(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_max_failures_per_ip", 6)
    for n in range(6):  # one failure each, so no single account ever reaches its own limit
        assert (await attempt(client, f"victim{n}@example.com")).status_code == 401
    assert (await attempt(client, "victim-new@example.com")).status_code == 429


async def test_the_lockout_ends_by_itself(client, user, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_window_seconds", 1)
    await fail_times(client, user.email, 5)
    assert (await attempt(client, user.email, PASSWORD)).status_code == 429
    await asyncio.sleep(1.3)
    assert (await attempt(client, user.email, PASSWORD)).status_code == 200


async def test_the_window_starts_at_the_first_failure_and_does_not_slide(client, user, monkeypatch):
    monkeypatch.setattr(get_settings(), "login_window_seconds", 3)
    await attempt(client, user.email)
    await asyncio.sleep(1.2)
    await attempt(client, user.email)  # a later failure must not push the expiry back
    redis = get_limiter()._redis
    (key,) = [k async for k in redis.scan_iter("login:fail:*")]
    assert 0 < await redis.ttl(key) <= 2


async def test_the_counters_expire_on_their_own(client, user):
    await attempt(client, user.email)
    redis = get_limiter()._redis
    for key in [k async for k in redis.scan_iter("login:fail*")]:
        assert 0 < await redis.ttl(key) <= get_settings().login_window_seconds


async def test_a_redis_outage_does_not_stop_anyone_signing_in(client, user):
    app.dependency_overrides[get_limiter] = lambda: RateLimiter("redis://localhost:1/0")
    try:
        assert (await attempt(client, user.email, PASSWORD)).status_code == 200
        assert (await attempt(client, user.email)).status_code == 401  # a normal failure, not a 500
    finally:
        app.dependency_overrides.pop(get_limiter, None)


async def test_other_endpoints_are_not_affected_by_a_lockout(client, user, auth_headers):
    headers = await auth_headers(user)
    await fail_times(client, user.email, 5)
    assert (await client.get("/api/auth/me", headers=headers)).status_code == 200
    assert (await client.get("/api/health")).status_code == 200
