"""Run the real Alembic migrations in a scratch database.

Every other test builds its schema from the models, which cannot notice a migration that is missing
something the models assume (a sequence, an enum, a constraint). This one can.
"""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
import pytest
from sqlalchemy.engine import make_url

from app.core.config import get_settings

BACKEND = Path(__file__).resolve().parent.parent


def alembic(database_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND,
        env={**os.environ, "DATABASE_URL": database_url},
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
async def scratch_database():
    base = make_url(get_settings().database_url)
    name = f"deskflow_migrations_{uuid.uuid4().hex[:8]}"
    dsn = base.set(drivername="postgresql").render_as_string(hide_password=False)
    admin = await asyncpg.connect(
        base.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
    )
    await admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield (
            base.set(database=name).render_as_string(hide_password=False),
            dsn.rsplit("/", 1)[0] + f"/{name}",
        )
    finally:
        await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await admin.close()


async def test_migrations_build_a_working_schema_and_round_trip(scratch_database):
    sqlalchemy_url, asyncpg_dsn = scratch_database
    sqlalchemy_url = sqlalchemy_url.replace("postgresql://", "postgresql+asyncpg://")

    up = alembic(sqlalchemy_url, "upgrade", "head")
    assert up.returncode == 0, up.stderr

    # The models and the migrations describe the same tables and columns.
    check = alembic(sqlalchemy_url, "check")
    assert check.returncode == 0, check.stdout + check.stderr

    conn = await asyncpg.connect(asyncpg_dsn)
    try:
        # Things autogenerate cannot see, and which the app depends on:
        assert await conn.fetchval("SELECT nextval('asset_tag_seq')") == 1
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO assets (asset_tag, type, manufacturer, model, status)"
                " VALUES ('X', 'laptop', 'a', 'b', 'assigned')"
            )
    finally:
        await conn.close()

    down = alembic(sqlalchemy_url, "downgrade", "base")
    assert down.returncode == 0, down.stderr
    again = alembic(sqlalchemy_url, "upgrade", "head")
    assert again.returncode == 0, again.stderr
