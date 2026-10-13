from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import STAFF_ROLES, is_staff
from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models.asset import ASSET_TAG_SEQ, Asset, AssetStatus, AssetType, ticket_assets
from app.models.audit import AuditLog
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.asset import (
    WARRANTY_WARNING_DAYS,
    AssetCreate,
    AssetPage,
    AssetRead,
    AssetStatusChange,
    AssetUpdate,
    AssignmentChange,
)
from app.schemas.audit import AuditLogRead
from app.schemas.ticket import TicketRead
from app.services import audit
from app.services.asset_workflow import can_transition

router = APIRouter(prefix="/assets", tags=["assets"])

StaffUser = Annotated[User, Depends(require_roles(*STAFF_ROLES))]

TRACKED_FIELDS = (
    "type",
    "manufacturer",
    "model",
    "serial_number",
    "status",
    "assigned_to_id",
    "location",
    "purchase_date",
    "warranty_expires_on",
    "notes",
)
REQUIRED_FIELDS = ("type", "manufacturer", "model")
CONFLICT = "An asset with that tag or serial number already exists"


def _snapshot(asset: Asset) -> dict[str, object]:
    return {f: getattr(asset, f) for f in TRACKED_FIELDS}


def _today() -> date:
    return datetime.now(UTC).date()


async def get_asset(session: AsyncSession, asset_id: int, user: User) -> Asset:
    asset = await session.get(Asset, asset_id)
    # Requesters can only see equipment assigned to them; anything else is "not found".
    if asset is None or (not is_staff(user) and asset.assigned_to_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Asset not found")
    return asset


async def _commit(session: AsyncSession) -> None:
    """Commit, turning a lost uniqueness race into a 409 instead of a 500."""
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, CONFLICT) from None


async def _ensure_unique(
    session: AsyncSession, tag: str | None, serial: str | None, own_id: int | None = None
) -> None:
    for column, value in ((Asset.asset_tag, tag), (Asset.serial_number, serial)):
        if value is None:
            continue
        stmt = select(Asset.id).where(column == value)
        if own_id is not None:
            stmt = stmt.where(Asset.id != own_id)
        if await session.scalar(stmt):
            raise HTTPException(status.HTTP_409_CONFLICT, CONFLICT)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_asset(session: SessionDep, user: StaffUser, body: AssetCreate) -> AssetRead:
    serial = body.serial_number or None
    await _ensure_unique(session, body.asset_tag, serial)

    tag = body.asset_tag
    if tag is None:
        number = await session.scalar(select(ASSET_TAG_SEQ.next_value()))
        tag = f"DF-{number:05d}"

    asset = Asset(
        asset_tag=tag,
        type=body.type,
        manufacturer=body.manufacturer,
        model=body.model,
        serial_number=serial,
        status=AssetStatus.IN_STOCK,
        location=body.location or None,
        purchase_date=body.purchase_date,
        warranty_expires_on=body.warranty_expires_on,
        notes=body.notes or None,
    )
    session.add(asset)
    await session.flush()
    audit.record(
        session, user, "asset", asset.id, "created", {"asset_tag": tag, **_snapshot(asset)}
    )
    await _commit(session)
    await session.refresh(asset)
    return AssetRead.model_validate(asset)


@router.get("")
async def list_assets(
    session: SessionDep,
    user: CurrentUser,
    status_: Annotated[AssetStatus | None, Query(alias="status")] = None,
    type_: Annotated[AssetType | None, Query(alias="type")] = None,
    assigned_to_id: int | None = None,
    warranty: Literal["expiring", "expired"] | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssetPage:
    stmt = select(Asset)
    if not is_staff(user):
        stmt = stmt.where(Asset.assigned_to_id == user.id)
    elif assigned_to_id is not None:
        stmt = stmt.where(Asset.assigned_to_id == assigned_to_id)
    if status_:
        stmt = stmt.where(Asset.status == status_)
    if type_:
        stmt = stmt.where(Asset.type == type_)
    if warranty:
        today = _today()
        if warranty == "expired":
            stmt = stmt.where(Asset.warranty_expires_on < today)
        else:
            stmt = stmt.where(
                Asset.warranty_expires_on.between(
                    today, today + timedelta(days=WARRANTY_WARNING_DAYS)
                )
            )
        # Retired equipment no longer needs warranty attention.
        stmt = stmt.where(Asset.status != AssetStatus.RETIRED)
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Asset.asset_tag.ilike(pattern),
                Asset.manufacturer.ilike(pattern),
                Asset.model.ilike(pattern),
                Asset.serial_number.ilike(pattern),
                Asset.location.ilike(pattern),
            )
        )

    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(stmt.order_by(Asset.asset_tag).limit(limit).offset(offset))
    return AssetPage(items=[AssetRead.model_validate(a) for a in rows], total=total)


@router.get("/{asset_id}")
async def read_asset(session: SessionDep, user: CurrentUser, asset_id: int) -> AssetRead:
    return AssetRead.model_validate(await get_asset(session, asset_id, user))


@router.patch("/{asset_id}")
async def update_asset(
    session: SessionDep, user: StaffUser, asset_id: int, body: AssetUpdate
) -> AssetRead:
    asset = await get_asset(session, asset_id, user)
    updates = body.model_dump(exclude_unset=True)
    # Optional fields can be cleared with null; the required ones cannot.
    if any(updates.get(f, "") is None for f in REQUIRED_FIELDS):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Required field cannot be null")
    for field in ("serial_number", "location", "notes"):
        if field in updates:
            updates[field] = updates[field] or None
    if "serial_number" in updates:
        await _ensure_unique(session, None, updates["serial_number"], own_id=asset.id)

    before = _snapshot(asset)
    for field, value in updates.items():
        setattr(asset, field, value)
    if changes := audit.diff(before, _snapshot(asset)):
        audit.record(session, user, "asset", asset.id, "updated", changes)
    await _commit(session)
    await session.refresh(asset)
    return AssetRead.model_validate(asset)


@router.post("/{asset_id}/status")
async def change_status(
    session: SessionDep, user: StaffUser, asset_id: int, body: AssetStatusChange
) -> AssetRead:
    asset = await get_asset(session, asset_id, user)
    if not can_transition(asset.status, body.status):
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Cannot move asset from {asset.status} to {body.status}"
        )
    before = _snapshot(asset)
    asset.status = body.status
    asset.assigned_to_id = None  # an assigned asset sent for repair or retired is taken back
    audit.record(
        session, user, "asset", asset.id, "status_changed", audit.diff(before, _snapshot(asset))
    )
    await _commit(session)
    await session.refresh(asset)
    return AssetRead.model_validate(asset)


@router.put("/{asset_id}/assignment")
async def assign_asset(
    session: SessionDep, user: StaffUser, asset_id: int, body: AssignmentChange
) -> AssetRead:
    asset = await get_asset(session, asset_id, user)
    before = _snapshot(asset)

    if body.assigned_to_id is None:
        if asset.status != AssetStatus.ASSIGNED:
            raise HTTPException(status.HTTP_409_CONFLICT, "Asset is not assigned")
        asset.assigned_to_id = None
        asset.status = AssetStatus.IN_STOCK
        action = "unassigned"
    else:
        if asset.status not in (AssetStatus.IN_STOCK, AssetStatus.ASSIGNED):
            raise HTTPException(
                status.HTTP_409_CONFLICT, f"A {asset.status} asset cannot be assigned"
            )
        assignee = await session.get(User, body.assigned_to_id)
        if assignee is None or not assignee.is_active:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Unknown user")
        asset.assigned_to_id = assignee.id
        asset.status = AssetStatus.ASSIGNED
        action = "assigned"

    if changes := audit.diff(before, _snapshot(asset)):
        audit.record(session, user, "asset", asset.id, action, changes)
    await _commit(session)
    await session.refresh(asset)
    return AssetRead.model_validate(asset)


@router.get("/{asset_id}/history")
async def asset_history(session: SessionDep, user: StaffUser, asset_id: int) -> list[AuditLogRead]:
    await get_asset(session, asset_id, user)
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "asset", AuditLog.entity_id == asset_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return [AuditLogRead.model_validate(r) for r in rows]


@router.get("/{asset_id}/tickets")
async def asset_tickets(session: SessionDep, user: StaffUser, asset_id: int) -> list[TicketRead]:
    await get_asset(session, asset_id, user)
    rows = await session.scalars(
        select(Ticket)
        .join(ticket_assets, ticket_assets.c.ticket_id == Ticket.id)
        .where(ticket_assets.c.asset_id == asset_id)
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
    )
    return [TicketRead.model_validate(t) for t in rows]
