import pytest
from sqlalchemy import select

from app.core.security import verify_password
from app.create_admin import MIN_PASSWORD_LENGTH, ensure_admin
from app.models import Role, User

PASSWORD = "a-long-enough-passphrase"


async def user_by_email(session, email):
    return await session.scalar(select(User).where(User.email == email))


async def test_creates_an_active_admin_who_can_sign_in(client, session):
    assert await ensure_admin(session, "Boss@Example.com", "The Boss", PASSWORD) == "created"
    user = await user_by_email(session, "boss@example.com")  # stored lower-case
    assert user.role == Role.ADMIN and user.is_active and user.full_name == "The Boss"
    assert verify_password(PASSWORD, user.hashed_password)
    assert user.hashed_password != PASSWORD

    res = await client.post(
        "/api/auth/login", data={"username": "boss@example.com", "password": PASSWORD}
    )
    assert res.status_code == 200


async def test_running_it_again_changes_nothing(session):
    await ensure_admin(session, "boss@example.com", "The Boss", PASSWORD)
    before = (await user_by_email(session, "boss@example.com")).hashed_password
    assert (
        await ensure_admin(session, "boss@example.com", "Someone Else", "another-long-passphrase")
        == "exists"
    )
    after = await user_by_email(session, "boss@example.com")
    assert after.hashed_password == before
    assert after.full_name == "The Boss"


async def test_it_never_promotes_or_re_passwords_an_existing_ordinary_user(session, make_user):
    existing = await make_user(Role.REQUESTER, "someone@example.com")
    original_hash = existing.hashed_password

    assert await ensure_admin(session, "someone@example.com", "Someone", PASSWORD) == "exists"
    user = await user_by_email(session, "someone@example.com")
    assert user.role == Role.REQUESTER  # a deploy variable must not be able to escalate a user
    assert user.hashed_password == original_hash


@pytest.mark.parametrize("password", ["", "short", "x" * (MIN_PASSWORD_LENGTH - 1)])
async def test_rejects_a_weak_password_without_creating_anything(session, password):
    with pytest.raises(ValueError, match="at least 12 characters"):
        await ensure_admin(session, "boss@example.com", "Boss", password)
    assert await user_by_email(session, "boss@example.com") is None


@pytest.mark.parametrize("email", ["", "not-an-email", "a@", "@example.com"])
async def test_rejects_an_invalid_email(session, email):
    with pytest.raises(ValueError, match="not a valid email"):
        await ensure_admin(session, email, "Boss", PASSWORD)


async def test_the_error_never_contains_the_password(session):
    with pytest.raises(ValueError) as caught:
        await ensure_admin(session, "boss@example.com", "Boss", "tiny-secret")
    assert "tiny-secret" not in str(caught.value)


async def test_a_blank_name_falls_back_to_a_default(session):
    await ensure_admin(session, "boss@example.com", "   ", PASSWORD)
    assert (await user_by_email(session, "boss@example.com")).full_name == "Administrator"
