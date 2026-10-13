# DeskFlow

**IT helpdesk and asset management platform**: a small service desk inspired by tools like ServiceNow.

[![CI](https://github.com/sam-razavi/deskflow/actions/workflows/ci.yml/badge.svg)](https://github.com/sam-razavi/deskflow/actions/workflows/ci.yml)

Built with **Angular 22**, **FastAPI**, **PostgreSQL** and **Redis**, containerised with Docker and deployed on Railway.

<p>
  <img src="docs/screenshots/tickets.png" width="49%" alt="Ticket list with filters, status and priority badges" />
  <img src="docs/screenshots/ticket-detail.png" width="49%" alt="Ticket detail with conversation, internal note, assignment and history" />
</p>

## Features

| Module | Status |
|---|---|
| Authentication: JWT access and refresh tokens, role-based access (Requester / Agent / Admin) | ✅ |
| Tickets: status workflow, priorities P1–P4, categories, comments with staff-only internal notes, assignment, search, filters and pagination | ✅ |
| SLA timers: response and resolution targets per priority, background breach detection, pause while pending | 🚧 |
| Audit log: append-only record of every ticket change (who, what, when, before/after), shown as a per-ticket history for staff and queryable by admins via the API. Admin UI and asset coverage still to come | 🟡 |
| Hardware inventory: assets, lifecycle status, assignment to users, links to tickets | 🚧 |
| Knowledge base: Markdown articles, draft/published, Postgres full-text search | 🚧 |
| Dashboard: open tickets by priority, SLA breaches, personal queue | 🚧 (placeholder) |

**Planned (phase 2):** AI troubleshooting assistant (retrieval over *published* KB articles only, via pgvector), email notifications, CSV asset import/export, attachments.

## How tickets work

- **Workflow:** `New → In progress ⇄ Pending → Resolved → Closed`. Resolved tickets can be reopened, and Closed is final. Invalid moves are rejected with `409`. The rules live in one place, `backend/app/services/workflow.py`.
- **Roles:** requesters see and edit only their own tickets (and only while still New), can add comments, and can confirm or reopen a resolved ticket. Agents and admins see everything, change priority, assign tickets and write internal notes. Another user's ticket returns `404`, not `403`, so ids can't be probed.
- **Assignment:** only agents and admins can be assignees. Assigning a New ticket moves it to In progress.
- **Audit trail:** every write records who did it and the before/after values in the same database transaction as the change, so a rolled-back request leaves no trace.

## Architecture

```
            ┌──────────────────────┐        ┌────────────────────┐
 Browser ──▶│ web (nginx + Angular)│──/api─▶│ api (FastAPI)      │──▶ PostgreSQL
            └──────────────────────┘        │  └ worker (arq)    │──▶ Redis
                                            └────────────────────┘
```

- **Same-origin API.** nginx serves the Angular build and reverse-proxies `/api` to the backend, so production needs no CORS. In development, `ng serve` does the same with `proxy.conf.json`.
- **Async all the way down.** SQLAlchemy 2.0 async with asyncpg, and Alembic migrations that run automatically on deploy.
- **Real-database tests.** Backend tests run against PostgreSQL (not SQLite). Each test runs in a transaction that is rolled back afterwards.

### Tech choices

| Area | Choice |
|---|---|
| Frontend | Angular 22 (standalone components, signals, built-in control flow, functional guards and interceptors), Angular Material 3, Vitest |
| Backend | FastAPI, SQLAlchemy 2.0 (async), Pydantic v2, Alembic, PyJWT, Argon2 password hashing |
| Data | PostgreSQL 16, Redis 7 (background jobs, caching, rate limiting) |
| Tooling | uv, Ruff, mypy (strict), pytest, Prettier, GitHub Actions, Docker Compose |

## Getting started

### Everything in Docker

```bash
docker compose up --build
```

Open http://localhost:4200. API docs (Swagger) are at http://localhost:8000/docs.

### Local development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), Node 22.22.3+ (or 24), and Docker for Postgres and Redis.

```bash
docker compose up -d db redis

# Backend
cd backend
cp .env.example .env
uv sync
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload

# Frontend (second terminal)
cd frontend
npm install
npm start          # http://localhost:4200, proxies /api to :8000
```

### Demo accounts

All demo accounts use the password `deskflow123`.

| Role | Email |
|---|---|
| Admin | admin@deskflow.dev |
| Agent | agent@deskflow.dev |
| Requester | user@deskflow.dev |

## Testing

```bash
# Backend (needs Postgres; uses the deskflow_test database)
cd backend
uv run pytest
uv run ruff check . && uv run mypy app

# Frontend
cd frontend
npx ng test --watch=false
```

## Deployment (Railway)

The project has one Railway project with four services:

1. **PostgreSQL** and **Redis**, from Railway's database templates.
2. **api**, with root directory `backend/`. Set these variables:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}` (the `postgres://` scheme is converted to asyncpg automatically)
   - `REDIS_URL=${{Redis.REDIS_URL}}`
   - `JWT_SECRET`: generate with `openssl rand -hex 32`
   - `ENVIRONMENT=production`
   - `PORT=8000`, which pins the port so the web service can reach the API over private networking
3. **web**, with root directory `frontend/`. Set `API_UPSTREAM=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` and give the service a public domain.

On every deploy the api container runs migrations and seeds the demo accounts (set `SEED_DEMO_DATA=false` to disable seeding).

## Project structure

```
backend/
  app/
    api/         routes and dependencies (auth, role checks)
    core/        settings, database, security
    models/      SQLAlchemy models (users, tickets, comments, audit logs)
    schemas/     Pydantic request and response models
    services/    business rules (ticket workflow, audit recording)
  alembic/       migrations
  tests/
frontend/
  src/app/
    core/        auth, ticket and user API services, interceptor, guards
    layout/      app shell (sidenav and toolbar)
    features/    one folder per feature (login, dashboard, tickets, ...)
```
