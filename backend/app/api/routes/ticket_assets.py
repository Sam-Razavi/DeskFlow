"""Linking tickets to the equipment they are about."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, insert, select

from app.api.access import is_staff, load_ticket
from app.api.deps import CurrentUser, SessionDep
from app.api.routes.assets import get_asset
from app.models.asset import Asset, ticket_assets
from app.models.ticket import TicketStatus
from app.schemas.asset import AssetRead
from app.services import audit

router = APIRouter(prefix="/tickets/{ticket_id}/assets", tags=["tickets"])


@router.get("")
async def list_linked_assets(
    session: SessionDep, user: CurrentUser, ticket_id: int
) -> list[AssetRead]:
    await load_ticket(session, ticket_id, user)
    stmt = (
        select(Asset)
        .join(ticket_assets, ticket_assets.c.asset_id == Asset.id)
        .where(ticket_assets.c.ticket_id == ticket_id)
        .order_by(Asset.asset_tag)
    )
    if not is_staff(user):
        # A requester only ever sees their own equipment, even if staff linked something else.
        stmt = stmt.where(Asset.assigned_to_id == user.id)
    return [AssetRead.model_validate(a) for a in await session.scalars(stmt)]


@router.put("/{asset_id}")
async def link_asset(
    session: SessionDep, user: CurrentUser, ticket_id: int, asset_id: int
) -> AssetRead:
    ticket = await load_ticket(session, ticket_id, user)
    asset = await get_asset(session, asset_id, user)  # a requester can only link their own
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed")

    already = await session.scalar(
        select(ticket_assets.c.asset_id).where(
            ticket_assets.c.ticket_id == ticket.id, ticket_assets.c.asset_id == asset.id
        )
    )
    if already is None:  # linking twice is harmless, and only the first time is worth auditing
        await session.execute(insert(ticket_assets).values(ticket_id=ticket.id, asset_id=asset.id))
        audit.record(
            session,
            user,
            "ticket",
            ticket.id,
            "asset_linked",
            {"asset_id": asset.id, "asset_tag": asset.asset_tag},
        )
        audit.record(session, user, "asset", asset.id, "ticket_linked", {"ticket_id": ticket.id})
        await session.commit()
    return AssetRead.model_validate(asset)


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_asset(
    session: SessionDep, user: CurrentUser, ticket_id: int, asset_id: int
) -> Response:
    ticket = await load_ticket(session, ticket_id, user)
    asset = await get_asset(session, asset_id, user)
    if ticket.status == TicketStatus.CLOSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Ticket is closed")

    result = await session.execute(
        delete(ticket_assets).where(
            ticket_assets.c.ticket_id == ticket.id, ticket_assets.c.asset_id == asset.id
        )
    )
    if result.rowcount:  # type: ignore[attr-defined]
        audit.record(
            session,
            user,
            "ticket",
            ticket.id,
            "asset_unlinked",
            {"asset_id": asset.id, "asset_tag": asset.asset_tag},
        )
        audit.record(session, user, "asset", asset.id, "ticket_unlinked", {"ticket_id": ticket.id})
        await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
