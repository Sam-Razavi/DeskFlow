import os

# Must be set before the app (and its engine) is imported.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://deskflow:deskflow@localhost:5432/deskflow_test"
)

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.db import get_session
from app.core.security import create_token, hash_password
from app.main import app
from app.models import Base, Role, User

PASSWORD = "password123"
# Argon2 is deliberately slow, so hash once and reuse it for every test user.
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session")
async def engine():
    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine) -> AsyncIterator[AsyncSession]:
    # Each test runs inside a transaction that is rolled back afterwards.
    async with engine.connect() as conn:
        trans = await conn.begin()
        maker = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with maker() as s:
            yield s
        await trans.rollback()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def make_user(session: AsyncSession):
    async def _make(role: Role = Role.REQUESTER, email: str | None = None) -> User:
        user = User(
            email=email or f"{role.value}@example.com",
            full_name=f"Test {role.value.title()}",
            role=role,
            hashed_password=PASSWORD_HASH,
        )
        session.add(user)
        await session.flush()
        return user

    return _make


@pytest.fixture
def auth_headers():
    """Issue a token directly; the login flow itself is covered in test_auth.py."""

    async def _headers(user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(str(user.id), 'access')}"}

    return _headers


@pytest.fixture
async def people(make_user, auth_headers):
    """A requester, a second requester, an agent and an admin, each with auth headers."""
    out = {}
    for key, role, email in [
        ("req", Role.REQUESTER, "req@example.com"),
        ("other", Role.REQUESTER, "other@example.com"),
        ("agent", Role.AGENT, "agent@example.com"),
        ("admin", Role.ADMIN, "admin@example.com"),
    ]:
        user = await make_user(role, email)
        out[key] = (user, await auth_headers(user))
    return out
