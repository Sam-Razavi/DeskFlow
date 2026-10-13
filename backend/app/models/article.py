import enum
from datetime import datetime
from typing import Any

from sqlalchemy import Computed, DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.ticket import Category
from app.models.user import User


class ArticleStatus(enum.StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


# Title matches outrank body matches (weight A over B). Generated and stored by Postgres, so it is
# always in step with the text and needs no application code or triggers to maintain.
SEARCH_VECTOR_SQL = (
    "setweight(to_tsvector('english', coalesce(title, '')), 'A') || "
    "setweight(to_tsvector('english', coalesce(body, '')), 'B')"
)


class Article(TimestampMixin, Base):
    __tablename__ = "articles"
    __table_args__ = (
        Index("ix_articles_search_vector", "search_vector", postgresql_using="gin"),
        Index("ix_articles_status_published_at", "status", "published_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)  # Markdown
    category: Mapped[Category] = mapped_column(
        Enum(Category, name="article_category", values_callable=lambda e: [m.value for m in e])
    )
    status: Mapped[ArticleStatus] = mapped_column(
        Enum(ArticleStatus, name="article_status", values_callable=lambda e: [m.value for m in e]),
        default=ArticleStatus.DRAFT,
    )
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Deferred: it is large and only ever used inside SQL, never read into Python.
    search_vector: Mapped[Any] = mapped_column(
        TSVECTOR, Computed(SEARCH_VECTOR_SQL, persisted=True), deferred=True
    )

    author: Mapped[User] = relationship(lazy="selectin")
