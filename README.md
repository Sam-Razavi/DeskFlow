# DeskFlow

**IT helpdesk and asset management platform**: a small service desk inspired by tools like ServiceNow.

[![CI](https://github.com/sam-razavi/deskflow/actions/workflows/ci.yml/badge.svg)](https://github.com/sam-razavi/deskflow/actions/workflows/ci.yml)

Built with **Angular 22**, **FastAPI**, **PostgreSQL** and **Redis**, containerised with Docker and deployed on Railway.

<p>
  <img src="docs/screenshots/dashboard.png" width="32%" alt="Dashboard with open tickets, SLA tiles and a priority chart" />
  <img src="docs/screenshots/tickets.png" width="32%" alt="Ticket list with SLA status, filters and priority badges" />
  <img src="docs/screenshots/ticket-detail.png" width="32%" alt="Ticket detail with service-level panel, conversation and history" />
</p>

## Features

| Module | Status |
|---|---|
| Authentication: JWT access and refresh tokens, role-based access (Requester / Agent / Admin) | ✅ |
| Tickets: status workflow, priorities P1–P4, categories, comments with staff-only internal notes, assignment, search, filters and pagination | ✅ |
| SLA timers: response and resolution targets per priority, clock paused while a ticket is Pending, a background worker that flags tickets at risk or breached | ✅ |
| Audit log: append-only record of every ticket change (who, what, when, before/after), shown as a per-ticket history for staff and queryable by admins via the API. Admin UI and asset coverage still to come | 🟡 |
| Hardware inventory: assets, lifecycle status, assignment to users, links to tickets | 🚧 |
| Knowledge base: Markdown articles, draft/published, Postgres full-text search | 🚧 |
| Dashboard: open tickets, SLA breached / at risk, unassigned, my queue, and a priority chart, with each figure linking to the matching ticket list | ✅ |

**Planned (phase 2):** AI troubleshooting assistant (retrieval over *published* KB articles only, via pgvector), email notifications, CSV asset import/export, attachments.

## How tickets work

- **Workflow:** `New → In progress ⇄ Pending → Resolved → Closed`. Resolved tickets can be reopened, and Closed is final. Invalid moves are rejected with `409`. The rules live in one place, `backend/app/services/workflow.py`.
- **Roles:** requesters see and edit only their own tickets (and only while still New), can add comments, and can confirm or reopen a resolved ticket. Agents and admins see everything, change priority, assign tickets and write internal notes. Another user's ticket returns `404`, not `403`, so ids can't be probed.
- **Assignment:** only agents and admins can be assignees. Assigning a New ticket moves it to In progress.
- **SLA:** each priority has a response and a resolution target, stored as deadlines on the ticket.

  | Priority | First response | Resolution |
  |---|---|---|
  | P1 · Critical | 1 h | 4 h |
  | P2 · High | 4 h | 8 h |
  | P3 · Medium | 8 h | 24 h |
  | P4 · Low | 24 h | 72 h |

  The first public reply from staff (not an internal note, and not the requester) stops the response clock. Moving a ticket to **Pending** pauses both clocks, and when it leaves Pending the deadlines move back by the time spent waiting. A ticket is *at risk* once 75% of its resolution window has passed and *breached* when a deadline passes. Times are wall-clock, not business hours. Requesters don't see SLA information.
- **One source of truth:** `backend/app/services/sla.py` decides every SLA state. The API, the dashboard, the list filter and the worker all call it, so they can't disagree.
- **Audit trail:** every write records who did it and the before/after values in the same database transaction as the change, so a rolled-back request leaves no trace.

## Architecture

```
            ┌──────────────────────┐        ┌──────────────────┐
 Browser ──▶│ web (nginx + Angular)│──/api─▶│ api (FastAPI)    │──┐
            └──────────────────────┘        └──────────────────┘  ├──▶ PostgreSQL
                                            ┌──────────────────┐  │
                                            │ worker (arq)     │──┤
                                            │ SLA check, 1/min │──┴──▶ Redis
                                            └──────────────────┘
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

# Background worker for SLA monitoring (needs Redis; optional for local development)
uv run arq app.worker.WorkerSettings

# Frontend (another terminal)
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

The project has one Railway project with five services:

1. **PostgreSQL** and **Redis**, from Railway's database templates.
2. **api**, with root directory `backend/`. Set these variables:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}` (the `postgres://` scheme is converted to asyncpg automatically)
   - `REDIS_URL=${{Redis.REDIS_URL}}`
   - `JWT_SECRET`: generate with `openssl rand -hex 32`
   - `ENVIRONMENT=production`
   - `PORT=8000`, which pins the port so the web service can reach the API over private networking
3. **worker**, with root directory `backend/` and *Config file path* set to `/backend/railway.worker.json`. It starts `arq app.worker.WorkerSettings` instead of the web server. Give it the same `DATABASE_URL` and `REDIS_URL` as the api. It never runs migrations, so deploy the api first.
4. **web**, with root directory `frontend/`. Set `API_UPSTREAM=http://${{api.RAILWAY_PRIVATE_DOMAIN}}:8000` and give the service a public domain.

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
