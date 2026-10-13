"""Create the first administrator from ADMIN_EMAIL / ADMIN_PASSWORD (and optionally ADMIN_NAME).

Production starts with no users, because the public demo accounts are off by default. The start
script runs this when both variables are set. It is safe to run on every deploy: an existing
account is never changed, so the password in the environment cannot silently take over a user.

Run by hand with:  ADMIN_EMAIL=... ADMIN_PASSWORD=... python -m app.create_admin
"""

import asyncio
import logging
import os
import sys
from typing import Literal

from pydantic import TypeAdapter, ValidationError
from pydantic.networks import EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, User

logger = logging.getLogger("deskflow.create_admin")

MIN_PASSWORD_LENGTH = 12
_email = TypeAdapter(EmailStr)


async def ensure_admin(
    session: AsyncSession, email: str, name: str, password: str
) -> Literal["created", "exists"]:
    try:
        address = str(_email.validate_python(email)).lower()
    except ValidationError as err:
        raise ValueError(f"ADMIN_EMAIL is not a valid email address: {email!r}") from err
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"ADMIN_PASSWORD must be at least {MIN_PASSWORD_LENGTH} characters")

    if await session.scalar(select(User.id).where(User.email == address)):
        return "exists"  # never touched: not its password, not its role

    session.add(
        User(
            email=address,
            full_name=name.strip() or "Administrator",
            role=Role.ADMIN,
            hashed_password=hash_password(password),
        )
    )
    await session.commit()
    return "created"


async def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    name = os.environ.get("ADMIN_NAME", "Administrator")
    if not email or not password:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD.", file=sys.stderr)
        return 1
    try:
        async with SessionLocal() as session:
            outcome = await ensure_admin(session, email, name, password)
    except ValueError as err:
        print(str(err), file=sys.stderr)  # the message never contains the password
        return 1
    print(f"Administrator {email.lower()}: {outcome}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
