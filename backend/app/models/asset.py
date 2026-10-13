import enum
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Sequence,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.user import User


class AssetType(enum.StrEnum):
    LAPTOP = "laptop"
    DESKTOP = "desktop"
    MONITOR = "monitor"
    PHONE = "phone"
    PRINTER = "printer"
    NETWORK = "network"
    PERIPHERAL = "peripheral"
    OTHER = "other"


class AssetStatus(enum.StrEnum):
    IN_STOCK = "in_stock"
    ASSIGNED = "assigned"
    IN_REPAIR = "in_repair"
    RETIRED = "retired"


# Numbers for generated tags (DF-00042). A sequence, unlike max(id)+1, is safe under concurrency.
ASSET_TAG_SEQ = Sequence("asset_tag_seq", metadata=Base.metadata)

# Links a ticket to the equipment it is about.
ticket_assets = Table(
    "ticket_assets",
    Base.metadata,
    Column("ticket_id", ForeignKey("tickets.id", ondelete="CASCADE"), primary_key=True),
    Column("asset_id", ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("linked_at", DateTime(timezone=True), server_default=func.now()),
)


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        # The database itself guarantees an asset is assigned exactly when it has an assignee,
        # so no code path (or manual SQL) can leave the two out of step.
        CheckConstraint(
            "(status = 'assigned') = (assigned_to_id IS NOT NULL)",
            name="assignment_matches_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(32), unique=True)
    type: Mapped[AssetType] = mapped_column(
        Enum(AssetType, name="asset_type", values_callable=lambda e: [m.value for m in e])
    )
    manufacturer: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(100))
    serial_number: Mapped[str | None] = mapped_column(String(100), unique=True)
    status: Mapped[AssetStatus] = mapped_column(
        Enum(AssetStatus, name="asset_status", values_callable=lambda e: [m.value for m in e]),
        default=AssetStatus.IN_STOCK,
    )
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    location: Mapped[str | None] = mapped_column(String(100))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    warranty_expires_on: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    assigned_to: Mapped[User | None] = relationship(lazy="selectin")
