"""Create demo accounts. Idempotent, safe to run on every deploy."""

import asyncio

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.user import Role, User

DEMO_USERS = [
    ("admin@deskflow.dev", "Ada Admin", Role.ADMIN),
    ("agent@deskflow.dev", "Alan Agent", Role.AGENT),
    ("user@deskflow.dev", "Grace User", Role.REQUESTER),
]
DEMO_PASSWORD = "deskflow123"


async def seed() -> None:
    async with SessionLocal() as session:
        for email, name, role in DEMO_USERS:
            if await session.scalar(select(User.id).where(User.email == email)):
                continue
            session.add(
                User(
                    email=email,
                    full_name=name,
                    role=role,
                    hashed_password=hash_password(DEMO_PASSWORD),
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
