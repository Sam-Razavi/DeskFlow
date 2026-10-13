# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Commits and pull requests

- All commits must be authored and committed solely by the repository owner:
  `Sam Sahbaei Razavi <h24sasah@du.se>`. Set this in the local git config before committing.
- Do **not** add `Co-Authored-By`, `Claude-Session` or any other AI attribution trailers to commit
  messages, and do not add "Generated with Claude Code" (or similar) lines to PR descriptions.
- Prefer small, focused commits, one logical change each.

## Project layout

- `backend/`: FastAPI + async SQLAlchemy + Alembic, managed with `uv`.
  - Checks: `uv run ruff check . && uv run ruff format --check . && uv run mypy app && uv run pytest`
  - Tests need Postgres with a `deskflow_test` database and Redis (`docker compose up -d db redis`).
    They use Redis database 15 and empty it, so never point `REDIS_URL` at one you care about.
  - Background worker (SLA monitor): `uv run arq app.worker.WorkerSettings`; it needs Redis. In
    containers the same image runs it when `SERVICE_ROLE=worker` (see `backend/start.sh`).
  - Do not add `railway.json`/`railway.toml`: Railway is retiring them (2026-12-01). Deployment is
    configured with a root directory and variables, documented in the README.
  - SLA rules live in `app/services/sla.py` and are the single source of truth: the API, the worker
    and the dashboard all call them, so don't re-implement the state logic elsewhere.
- `backend/app/services/assistant.py`: the AI assistant. It must stay grounded: only retrieved published articles go to the model, and uncited answers are dropped.
- `frontend/`: Angular 22 + Angular Material, requires Node >= 22.22.3 (or 24).
  - Checks: `npx prettier --check "src/**/*.{ts,html,scss}" && npx ng test --watch=false && npx ng build`
  - `ng test` can serve stale compiled code from `node_modules/.vitest-cache`, so a source change may
    not show up in results. If a result looks wrong, or before trusting a green run, delete
    `node_modules/.vitest-cache` and `.angular` and run again. CI starts clean, so it is unaffected.
- The request's DB session does not commit by itself: a route that writes must `await session.commit()`.
  Tests share one rolled-back session, so a missing commit passes them; assert on it explicitly.
- The AI assistant (`app/services/assistant.py`) must stay grounded: only retrieved published articles reach
  the model, and an answer that cites none of them is dropped.
- Schema changes go through Alembic migrations (`uv run alembic revision --autogenerate -m "..."`).
