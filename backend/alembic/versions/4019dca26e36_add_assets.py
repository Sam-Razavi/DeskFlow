"""add assets

Revision ID: 4019dca26e36
Revises: 015b07a57145
Create Date: 2026-10-13 06:21:56.467162

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4019dca26e36"
down_revision: str | Sequence[str] | None = "015b07a57145"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Alembic does not autogenerate standalone sequences; asset tags (DF-00042) draw from this one.
    op.execute(sa.schema.CreateSequence(sa.Sequence("asset_tag_seq")))
    op.create_table(
        "assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("asset_tag", sa.String(length=32), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "laptop",
                "desktop",
                "monitor",
                "phone",
                "printer",
                "network",
                "peripheral",
                "other",
                name="asset_type",
            ),
            nullable=False,
        ),
        sa.Column("manufacturer", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("serial_number", sa.String(length=100), nullable=True),
        sa.Column(
            "status",
            sa.Enum("in_stock", "assigned", "in_repair", "retired", name="asset_status"),
            nullable=False,
        ),
        sa.Column("assigned_to_id", sa.Integer(), nullable=True),
        sa.Column("location", sa.String(length=100), nullable=True),
        sa.Column("purchase_date", sa.Date(), nullable=True),
        sa.Column("warranty_expires_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "(status = 'assigned') = (assigned_to_id IS NOT NULL)",
            name=op.f("ck_assets_assignment_matches_status"),
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_id"], ["users.id"], name=op.f("fk_assets_assigned_to_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("asset_tag", name=op.f("uq_assets_asset_tag")),
        sa.UniqueConstraint("serial_number", name=op.f("uq_assets_serial_number")),
    )
    op.create_index(op.f("ix_assets_assigned_to_id"), "assets", ["assigned_to_id"], unique=False)
    op.create_table(
        "ticket_assets",
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=False),
        sa.Column(
            "linked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_ticket_assets_asset_id_assets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_ticket_assets_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ticket_id", "asset_id", name=op.f("pk_ticket_assets")),
    )
    op.create_index(op.f("ix_ticket_assets_asset_id"), "ticket_assets", ["asset_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_ticket_assets_asset_id"), table_name="ticket_assets")
    op.drop_table("ticket_assets")
    op.drop_index(op.f("ix_assets_assigned_to_id"), table_name="assets")
    op.drop_table("assets")
    for name in ("asset_type", "asset_status"):
        sa.Enum(name=name).drop(op.get_bind(), checkfirst=True)
    op.execute(sa.schema.DropSequence(sa.Sequence("asset_tag_seq")))
