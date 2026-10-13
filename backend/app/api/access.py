"""Authorisation helpers shared by several route modules."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket
from app.models.user import Role, User

STAFF_ROLES = (Role.AGENT, Role.ADMIN)


def is_staff(user: User) -> bool:
    return user.role in STAFF_ROLES


async def load_ticket(session: AsyncSession, ticket_id: int, user: User) -> Ticket:
    ticket = await session.get(Ticket, ticket_id)
    # Requesters get a 404 (not 403) for other people's tickets so ids can't be probed.
    if ticket is None or (not is_staff(user) and ticket.requester_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ticket not found")
    return ticket
