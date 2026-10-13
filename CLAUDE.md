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
  - Tests need Postgres with a `deskflow_test` database (`docker compose up -d db`).
- `frontend/`: Angular 22 + Angular Material, requires Node >= 22.22.3 (or 24).
  - Checks: `npx prettier --check "src/**/*.{ts,html,scss}" && npx ng test --watch=false && npx ng build`
- Schema changes go through Alembic migrations (`uv run alembic revision --autogenerate -m "..."`).
