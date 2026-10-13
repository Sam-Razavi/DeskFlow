"""Create demo accounts and knowledge-base articles. Idempotent, safe to run on every deploy."""

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.demo_articles import DEMO_ARTICLES
from app.models.article import Article, ArticleStatus
from app.models.user import Role, User
from app.services import sla

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

        author_id = await session.scalar(select(User.id).where(User.email == "agent@deskflow.dev"))
        assert author_id is not None
        existing = set(await session.scalars(select(Article.title)))
        now = sla.utcnow()
        for age, demo in enumerate(DEMO_ARTICLES):
            if demo.title in existing:
                continue
            published = demo.status == ArticleStatus.PUBLISHED
            session.add(
                Article(
                    title=demo.title,
                    body=demo.body,
                    category=demo.category,
                    status=demo.status,
                    author_id=author_id,
                    # Spread the dates out so the list has a natural order.
                    published_at=now - timedelta(days=age * 3 + 1) if published else None,
                )
            )
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
