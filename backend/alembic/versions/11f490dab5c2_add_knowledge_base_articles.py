"""add knowledge base articles

Revision ID: 11f490dab5c2
Revises: 4019dca26e36
Create Date: 2026-10-13 07:22:26.071156

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11f490dab5c2"
down_revision: str | Sequence[str] | None = "4019dca26e36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "articles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "category",
            sa.Enum("hardware", "software", "network", "access", "other", name="article_category"),
            nullable=False,
        ),
        sa.Column("status", sa.Enum("draft", "published", name="article_status"), nullable=False),
        sa.Column("author_id", sa.Integer(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "setweight(to_tsvector('english', coalesce(title, '')), 'A') || setweight(to_tsvector('english', coalesce(body, '')), 'B')",  # noqa: E501
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["author_id"], ["users.id"], name=op.f("fk_articles_author_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_articles")),
    )
    op.create_index(
        "ix_articles_search_vector",
        "articles",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_articles_status_published_at", "articles", ["status", "published_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_articles_status_published_at", table_name="articles")
    op.drop_index("ix_articles_search_vector", table_name="articles", postgresql_using="gin")
    op.drop_table("articles")
    for name in ("article_category", "article_status"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
