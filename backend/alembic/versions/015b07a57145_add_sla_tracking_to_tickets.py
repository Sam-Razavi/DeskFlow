"""add sla tracking to tickets

Revision ID: 015b07a57145
Revises: 9ef143dbe6ff
Create Date: 2026-10-13 01:08:15.350433

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "015b07a57145"
down_revision: str | Sequence[str] | None = "9ef143dbe6ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tickets", sa.Column("first_response_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("resolution_due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("tickets", sa.Column("sla_paused_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tickets", sa.Column("sla_paused_seconds", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "tickets", sa.Column("resolution_at_risk_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("response_breached_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tickets", sa.Column("resolution_breached_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Backfill existing tickets with the same targets as app.services.sla.TARGETS.
    op.execute("""
        UPDATE tickets SET
          response_due_at = created_at + CASE priority
            WHEN 'p1' THEN interval '1 hour'
            WHEN 'p2' THEN interval '4 hours'
            WHEN 'p3' THEN interval '8 hours'
            ELSE interval '24 hours' END,
          resolution_due_at = created_at + CASE priority
            WHEN 'p1' THEN interval '4 hours'
            WHEN 'p2' THEN interval '8 hours'
            WHEN 'p3' THEN interval '24 hours'
            ELSE interval '72 hours' END
    """)
    # A first response is the earliest public reply from staff other than the requester.
    op.execute("""
        UPDATE tickets SET first_response_at = (
          SELECT min(c.created_at) FROM ticket_comments c
          JOIN users u ON u.id = c.author_id
          WHERE c.ticket_id = tickets.id
            AND NOT c.is_internal
            AND u.role::text IN ('agent', 'admin')
            AND c.author_id <> tickets.requester_id)
    """)
    op.alter_column("tickets", "response_due_at", nullable=False)
    op.alter_column("tickets", "resolution_due_at", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tickets", "resolution_breached_at")
    op.drop_column("tickets", "response_breached_at")
    op.drop_column("tickets", "resolution_at_risk_at")
    op.drop_column("tickets", "sla_paused_seconds")
    op.drop_column("tickets", "sla_paused_at")
    op.drop_column("tickets", "resolution_due_at")
    op.drop_column("tickets", "response_due_at")
    op.drop_column("tickets", "first_response_at")
