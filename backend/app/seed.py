"""Create the demo: accounts, knowledge-base articles and a lived-in helpdesk.

Idempotent and safe to run on every deploy (start.sh does when demo data is on):

- accounts and articles are added only if missing, and the three documented accounts are never
  changed once they exist;
- tickets and equipment are only added to a helpdesk that has none, so sample data never mixes
  with real records.

The helpdesk is not inserted as finished rows. Its history (app.demo_data) is replayed in time
order through the same rules the API uses: SLA deadlines, the status workflow, assignment, the
first-reply rule, asset tags from the sequence, and an audit entry for every change at the moment
it happened. The SLA monitor is replayed too, once a minute like the worker, so tickets carry the
at-risk and breach flags (and their audit entries) the worker would have recorded. When the real
worker next runs, it finds nothing new to flag.

reset_demo() wipes the demo and creates it again relative to the current time. The worker runs it
daily when SEED_DEMO_DATA=true; see its docstring for the safeguards.
"""

import asyncio
import functools
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import exists, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import STAFF_ROLES
from app.api.routes.assets import TRACKED_FIELDS as ASSET_FIELDS
from app.api.routes.assets import next_asset_tag
from app.api.routes.tickets import TRACKED_FIELDS as TICKET_FIELDS
from app.core.config import Settings, get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.demo_articles import DEMO_ARTICLES
from app.demo_data import (
    ADMIN,
    AGENT,
    DEMO_ASSETS,
    DEMO_PASSWORD,
    DEMO_REQUESTERS,
    DEMO_TICKETS,
    DEMO_USERS,
    AssetAssign,
    AssetStatusChange,
    Assign,
    DemoAsset,
    DemoTicket,
    Escalate,
    Link,
    Note,
    Reply,
    Status,
    TicketStep,
)
from app.models.article import Article, ArticleStatus
from app.models.asset import Asset, AssetStatus, ticket_assets
from app.models.ticket import Ticket, TicketComment, TicketStatus
from app.models.user import Role, User
from app.services import asset_workflow, audit, sla, workflow
from app.services.sla_monitor import flag_ticket

logger = logging.getLogger("deskflow.seed")

# The worker checks SLAs at the start of every minute; the replay does the same.
MONITOR_INTERVAL = timedelta(minutes=1)


@dataclass(frozen=True)
class SeedResult:
    """How many of each record this run created (0 when they already existed)."""

    users: int
    articles: int
    tickets: int
    assets: int


async def seed(
    session: AsyncSession, *, settings: Settings | None = None, now: datetime | None = None
) -> SeedResult | None:
    """Add whatever part of the demo is missing. Returns None, creating nothing, when demo data is
    off. Leaves committing to the caller, so a reset can replace the demo in one transaction."""
    settings = settings or get_settings()
    if not settings.demo_data_enabled:
        return None
    now = now or sla.utcnow()

    users = await _seed_users(session)
    people = {u.email: u for u in await session.scalars(select(User))}
    articles = await _seed_articles(session, people[AGENT], now)
    tickets, assets = await _seed_helpdesk(session, people, now)
    return SeedResult(users=users, articles=articles, tickets=tickets, assets=assets)


# --- Accounts ---------------------------------------------------------------------------------


@functools.cache
def _demo_password_hash() -> str:
    return hash_password(DEMO_PASSWORD)  # public anyway, so one hash (and salt) serves all three


@functools.cache
def _unusable_password_hash() -> str:
    # A random password that is never stored or shown: these colleagues cannot sign in.
    return hash_password(secrets.token_urlsafe(32))


async def _seed_users(session: AsyncSession) -> int:
    existing = set(await session.scalars(select(User.email)))
    created = 0
    for email, name, role in DEMO_USERS:
        if email not in existing:
            hashed = _demo_password_hash()
            session.add(User(email=email, full_name=name, role=role, hashed_password=hashed))
            created += 1
    for email, name in DEMO_REQUESTERS:
        if email not in existing:
            hashed = _unusable_password_hash()
            session.add(
                User(email=email, full_name=name, role=Role.REQUESTER, hashed_password=hashed)
            )
            created += 1
    await session.flush()
    return created


# --- Knowledge base ---------------------------------------------------------------------------


async def _seed_articles(session: AsyncSession, author: User, now: datetime) -> int:
    existing = set(await session.scalars(select(Article.title)))
    created = 0
    for age, demo in enumerate(DEMO_ARTICLES):
        if demo.title in existing:
            continue
        published = demo.status == ArticleStatus.PUBLISHED
        # Spread the dates out so the list has a natural order.
        published_at = now - timedelta(days=age * 3 + 1) if published else None
        written_at = (published_at or now - timedelta(days=1)) - timedelta(hours=2)
        article = Article(
            title=demo.title,
            body=demo.body,
            category=demo.category,
            status=ArticleStatus.DRAFT,
            author_id=author.id,
            created_at=written_at,
            updated_at=published_at or written_at,
        )
        session.add(article)
        await session.flush()
        audit.record(
            session,
            author,
            "article",
            article.id,
            "created",
            {"title": article.title, "category": article.category, "status": article.status},
            at=written_at,
        )
        if published_at is not None:
            audit.record(
                session,
                author,
                "article",
                article.id,
                "published",
                {"status": [ArticleStatus.DRAFT, ArticleStatus.PUBLISHED]},
                at=published_at,
            )
            article.status = ArticleStatus.PUBLISHED
            article.published_at = published_at
        created += 1
    await session.flush()
    return created


# --- Helpdesk ---------------------------------------------------------------------------------


def _fields(obj: object, names: tuple[str, ...]) -> dict[str, Any]:
    return {name: getattr(obj, name) for name in names}


class _Replay:
    """Applies demo events one at a time, as the API would have when they happened."""

    def __init__(self, session: AsyncSession, people: dict[str, User], now: datetime) -> None:
        self.session = session
        self.people = people
        self.today = now.date()
        self.tickets: list[Ticket] = []
        self.assets: dict[str, Asset] = {}

    def person(self, email: str) -> User:
        try:
            return self.people[email]
        except KeyError:
            raise ValueError(f"Demo data names an unknown person: {email}") from None

    def staff(self, email: str) -> User:
        user = self.person(email)
        if user.role not in STAFF_ROLES:
            raise ValueError(f"Only staff can do that in the demo data: {email}")
        return user

    def asset(self, key: str) -> Asset:
        try:
            return self.assets[key]
        except KeyError:
            raise ValueError(f"Demo data names an unknown or later asset: {key}") from None

    def monitor(self, at: datetime) -> None:
        """One run of the worker's SLA check, at `at`."""
        for ticket in self.tickets:
            if flag_ticket(self.session, ticket, at):
                ticket.updated_at = at

    # Tickets

    async def open_ticket(self, demo: DemoTicket, at: datetime) -> Ticket:
        requester = self.person(demo.requester)
        actor = self.staff(demo.logged_by) if demo.logged_by else requester
        response_due, resolution_due = sla.due_dates(at, demo.priority)
        ticket = Ticket(
            title=demo.title,
            description=demo.description,
            status=TicketStatus.NEW,
            priority=demo.priority,
            category=demo.category,
            requester_id=requester.id,
            created_at=at,
            updated_at=at,
            response_due_at=response_due,
            resolution_due_at=resolution_due,
        )
        self.session.add(ticket)
        await self.session.flush()
        changes = {**_fields(ticket, TICKET_FIELDS), "requester_id": requester.id}
        audit.record(self.session, actor, "ticket", ticket.id, "created", changes, at=at)
        self.tickets.append(ticket)
        return ticket

    async def ticket_step(self, ticket: Ticket, step: TicketStep, at: datetime) -> None:
        if ticket.status == TicketStatus.CLOSED:
            raise ValueError(f"A step after the ticket was closed: {ticket.title}")
        before = _fields(ticket, TICKET_FIELDS)
        match step:
            case Assign(to=to, by=by):
                actor = self.staff(by)
                workflow.assign(ticket, self.staff(to).id, at)
                self._log_change(ticket, actor, "assigned", before, at)
            case Status(to=to, by=by):
                actor = self.person(by)
                if not workflow.can_transition(ticket.status, to, actor.role):
                    raise ValueError(f"{actor.email} cannot move {ticket.title!r} to {to}")
                workflow.apply_status(ticket, to, at)
                self._log_change(ticket, actor, "status_changed", before, at)
            case Escalate(to=to, by=by):
                actor = self.staff(by)
                ticket.priority = to
                sla.recompute(ticket)
                self._log_change(ticket, actor, "updated", before, at)
            case Reply(by=by, body=body):
                await self.comment(ticket, self.person(by), body, internal=False, at=at)
            case Note(by=by, body=body):
                await self.comment(ticket, self.staff(by), body, internal=True, at=at)
            case Link(asset=key, by=by):
                await self.link(ticket, self.asset(key), self.staff(by), at)
            case AssetAssign() | AssetStatusChange():
                self.asset_step(self.asset(step.asset), step, at)

    def _log_change(
        self, ticket: Ticket, actor: User, action: str, before: dict[str, Any], at: datetime
    ) -> None:
        ticket.updated_at = at
        changes = audit.diff(before, _fields(ticket, TICKET_FIELDS))
        audit.record(self.session, actor, "ticket", ticket.id, action, changes, at=at)

    async def comment(
        self, ticket: Ticket, author: User, body: str, *, internal: bool, at: datetime
    ) -> None:
        comment = TicketComment(
            ticket_id=ticket.id, author_id=author.id, body=body, is_internal=internal, created_at=at
        )
        self.session.add(comment)
        await self.session.flush()
        changes: dict[str, Any] = {"comment_id": comment.id, "is_internal": internal}
        if sla.register_reply(
            ticket,
            at,
            by_staff=author.role in STAFF_ROLES,
            by_requester=author.id == ticket.requester_id,
            internal=internal,
        ):
            changes["first_response"] = True
            ticket.updated_at = at
        audit.record(self.session, author, "ticket", ticket.id, "commented", changes, at=at)

    async def link(self, ticket: Ticket, asset: Asset, actor: User, at: datetime) -> None:
        await self.session.execute(
            insert(ticket_assets).values(ticket_id=ticket.id, asset_id=asset.id, linked_at=at)
        )
        audit.record(
            self.session,
            actor,
            "ticket",
            ticket.id,
            "asset_linked",
            {"asset_id": asset.id, "asset_tag": asset.asset_tag},
            at=at,
        )
        audit.record(
            self.session, actor, "asset", asset.id, "ticket_linked", {"ticket_id": ticket.id}, at=at
        )

    # Equipment

    async def register_asset(self, demo: DemoAsset, at: datetime) -> Asset:
        asset = Asset(
            asset_tag=await next_asset_tag(self.session),
            type=demo.type,
            manufacturer=demo.manufacturer,
            model=demo.model,
            serial_number=demo.serial_number,
            status=AssetStatus.IN_STOCK,
            location=demo.location,
            purchase_date=self.today - demo.purchased,
            warranty_expires_on=(
                self.today + demo.warranty_left if demo.warranty_left is not None else None
            ),
            notes=demo.notes,
            created_at=at,
            updated_at=at,
        )
        self.session.add(asset)
        await self.session.flush()
        changes = {"asset_tag": asset.asset_tag, **_fields(asset, ASSET_FIELDS)}
        audit.record(self.session, self.staff(ADMIN), "asset", asset.id, "created", changes, at=at)
        self.assets[demo.key] = asset
        return asset

    def asset_step(self, asset: Asset, step: AssetAssign | AssetStatusChange, at: datetime) -> None:
        actor = self.staff(step.by)
        before = _fields(asset, ASSET_FIELDS)
        if isinstance(step, AssetAssign):
            if asset.status not in (AssetStatus.IN_STOCK, AssetStatus.ASSIGNED):
                raise ValueError(f"A {asset.status} asset cannot be assigned: {asset.model}")
            asset.assigned_to_id = self.person(step.to).id
            asset.status = AssetStatus.ASSIGNED
            action = "assigned"
        else:
            if not asset_workflow.can_transition(asset.status, step.to):
                raise ValueError(f"Cannot move {asset.model} from {asset.status} to {step.to}")
            asset.status = step.to
            asset.assigned_to_id = None  # repair or retirement takes it back
            action = "status_changed"
        asset.updated_at = at
        changes = audit.diff(before, _fields(asset, ASSET_FIELDS))
        audit.record(self.session, actor, "asset", asset.id, action, changes, at=at)


Event = tuple[datetime, int, DemoTicket | DemoAsset, TicketStep | None]


def _timeline(now: datetime) -> list[Event]:
    """Every demo event with its time, in time order. Ties keep definition order, so a ticket or
    asset always comes before its own steps."""
    events: list[Event] = []
    owners: list[tuple[datetime, DemoTicket | DemoAsset]] = [
        (now - a.registered, a) for a in DEMO_ASSETS
    ] + [(now - t.age, t) for t in DEMO_TICKETS]
    for start, owner in owners:
        events.append((start, len(events), owner, None))
        for step in owner.steps:
            events.append((start + step.after, len(events), owner, step))
    events.sort(key=lambda e: (e[0], e[1]))
    if events[-1][0] > now:
        raise ValueError("Demo data has an event in the future")
    return events


async def _seed_helpdesk(
    session: AsyncSession, people: dict[str, User], now: datetime
) -> tuple[int, int]:
    has_tickets = await session.scalar(select(exists().select_from(Ticket)))
    has_assets = await session.scalar(select(exists().select_from(Asset)))
    if has_tickets or has_assets:
        return 0, 0  # a helpdesk in use: never mix sample records into it

    replay = _Replay(session, people, now)
    opened: dict[int, Ticket] = {}
    events = _timeline(now)
    tick = _next_minute(events[0][0])
    for at, _, owner, step in events:
        while tick <= at:
            replay.monitor(tick)
            tick += MONITOR_INTERVAL
        if isinstance(owner, DemoAsset):
            if step is None:
                await replay.register_asset(owner, at)
            else:
                assert isinstance(step, AssetAssign | AssetStatusChange)
                replay.asset_step(replay.asset(owner.key), step, at)
        elif step is None:
            opened[id(owner)] = await replay.open_ticket(owner, at)
        else:
            await replay.ticket_step(opened[id(owner)], step, at)
    while tick <= now:
        replay.monitor(tick)
        tick += MONITOR_INTERVAL

    await session.flush()
    return len(replay.tickets), len(replay.assets)


def _next_minute(at: datetime) -> datetime:
    start = at.replace(second=0, microsecond=0)
    return start if start == at else start + MONITOR_INTERVAL


# --- Daily reset ------------------------------------------------------------------------------

# Everything the demo creates except accounts. TRUNCATE without CASCADE: if a table that is not
# listed here ever references one of these, the reset fails instead of silently emptying it too.
DEMO_TABLES = ("ticket_assets", "ticket_comments", "tickets", "assets", "articles", "audit_logs")


class DemoResetRefused(RuntimeError):
    """The database is not a demo the reset may replace."""


async def reset_demo(
    session: AsyncSession, *, settings: Settings | None = None, now: datetime | None = None
) -> SeedResult:
    """Replace the demo's records with a fresh copy relative to `now`, in one transaction.

    For the public demo only: SLA timers are wall-clock, so a demo created once drifts into
    "everything breached" within days, and visitors' changes pile up. Running this daily keeps it
    looking like a working helpdesk.

    It deletes data, so it refuses (DemoResetRefused) unless both hold:

    - SEED_DEMO_DATA is explicitly true. No default enables it, not even in development;
    - the documented demo accounts exist with their roles, so this is a demo database.

    Tickets, comments, ticket links, equipment, articles and the audit log are emptied and the
    demo is created again; accounts are kept. Emptying the audit log is a deliberate exception to
    its append-only rule, which protects the history of records that exist. The reset restores a
    disposable fixture, like reloading a database snapshot: the records the log describes are
    gone, and keeping their entries would leave a growing pile of rows about records that no
    longer exist, interleaved with the new history. Id sequences and asset tags restart too, so
    the demo is the same every day. Visitors never see it half done: the transaction commits all
    of it or none.
    """
    settings = settings or get_settings()
    if not settings.demo_reset_enabled:
        raise DemoResetRefused("Demo reset needs SEED_DEMO_DATA=true")
    roles = {email: role for email, role in await session.execute(select(User.email, User.role))}
    missing = [email for email, _, role in DEMO_USERS if roles.get(email) != role]
    if missing:
        raise DemoResetRefused(f"Not a demo database: missing demo accounts {missing}")

    await session.execute(text(f"TRUNCATE {', '.join(DEMO_TABLES)} RESTART IDENTITY"))
    await session.execute(text("ALTER SEQUENCE asset_tag_seq RESTART"))
    session.expunge_all()  # anything loaded before the truncate is gone

    result = await seed(session, settings=settings, now=now)
    assert result is not None  # demo_reset_enabled implies demo_data_enabled
    await session.commit()
    return result


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    async with SessionLocal() as session:
        result = await seed(session)
        await session.commit()
    if result is None:
        logger.info("Demo data is off (SEED_DEMO_DATA); nothing created.")
    else:
        logger.info("Demo data created: %s", result)


if __name__ == "__main__":
    asyncio.run(main())
