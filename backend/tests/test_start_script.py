"""The container start script decides what actually runs in production, so test what it runs.

Real commands are replaced by stubs that record how they were called.
"""

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "start.sh"
COMMANDS = ("alembic", "python", "uvicorn", "arq")


@pytest.fixture
def run(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"

    def make_stubs(failing: str | None = None):
        for name in COMMANDS:
            stub = bin_dir / name
            exit_code = 1 if name == failing else 0
            stub.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit {exit_code}\n')
            stub.chmod(0o755)

    def execute(failing: str | None = None, **env: str):
        make_stubs(failing)
        log.write_text("")
        clean = {"PATH": f"{bin_dir}:/usr/bin:/bin", **env}
        result = subprocess.run(
            ["sh", str(SCRIPT)], env=clean, capture_output=True, text=True, check=False
        )
        calls = [line for line in log.read_text().splitlines() if line]
        return result, calls

    return execute


def test_api_by_default_migrates_seeds_for_development_and_serves(run):
    result, calls = run()
    assert result.returncode == 0
    assert calls == [
        "alembic upgrade head",
        "python -m app.seed",
        "uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips=*",
    ]


def test_production_does_not_create_publicly_known_demo_accounts_unless_asked(run):
    _, calls = run(ENVIRONMENT="production")
    assert "python -m app.seed" not in calls
    assert calls[0] == "alembic upgrade head"
    assert calls[-1].startswith("uvicorn ")


def test_production_seeds_when_explicitly_requested(run):
    _, calls = run(ENVIRONMENT="production", SEED_DEMO_DATA="true")
    assert "python -m app.seed" in calls


def test_seeding_can_be_switched_off_in_development(run):
    _, calls = run(SEED_DEMO_DATA="false")
    assert "python -m app.seed" not in calls


def test_the_first_admin_is_created_after_migrating_and_before_serving(run):
    _, calls = run(ENVIRONMENT="production", ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="x")
    assert calls[0] == "alembic upgrade head"
    assert calls[1] == "python -m app.create_admin"
    assert calls[-1].startswith("uvicorn ")


@pytest.mark.parametrize("env", [{}, {"ADMIN_EMAIL": "boss@example.com"}, {"ADMIN_PASSWORD": "x"}])
def test_no_admin_is_created_unless_both_variables_are_set(run, env):
    _, calls = run(ENVIRONMENT="production", **env)
    assert "python -m app.create_admin" not in calls


def test_the_worker_never_creates_users(run):
    _, calls = run(SERVICE_ROLE="worker", ADMIN_EMAIL="boss@example.com", ADMIN_PASSWORD="x")
    assert calls == ["arq app.worker.WorkerSettings"]


def test_port_and_host_come_from_the_environment(run):
    _, calls = run(PORT="9123", HOST="::")
    assert "--host :: --port 9123" in calls[-1]


def test_the_worker_role_starts_only_the_worker(run):
    result, calls = run(SERVICE_ROLE="worker")
    assert result.returncode == 0
    # No migrations, no seeding and no web server: the api service owns the schema.
    assert calls == ["arq app.worker.WorkerSettings"]


def test_an_unknown_role_fails_loudly_and_starts_nothing(run):
    result, calls = run(SERVICE_ROLE="wrker")
    assert result.returncode == 1
    assert "Unknown SERVICE_ROLE 'wrker'" in result.stderr
    assert calls == []


def test_a_failed_migration_stops_the_start_so_a_broken_release_never_serves(run):
    result, calls = run(failing="alembic")
    assert result.returncode == 1
    assert calls == ["alembic upgrade head"]


def test_a_failed_seed_also_stops_the_start(run):
    result, calls = run(failing="python")
    assert result.returncode == 1
    assert not any(c.startswith("uvicorn") for c in calls)
    assert os.path.exists(SCRIPT)
