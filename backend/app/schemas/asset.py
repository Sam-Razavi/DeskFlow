from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    computed_field,
    model_validator,
)

from app.models.asset import AssetStatus, AssetType
from app.schemas.ticket import UserBrief

WARRANTY_WARNING_DAYS = 30

Text100 = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
OptionalText100 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)]
AssetTag = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,31}$"
    ),
]


def _check_dates(purchase: date | None, warranty: date | None) -> None:
    if purchase and warranty and warranty < purchase:
        raise ValueError("Warranty cannot end before the purchase date")


class AssetCreate(BaseModel):
    # Generated (DF-00042) when left out.
    asset_tag: AssetTag | None = None
    type: AssetType
    manufacturer: Text100
    model: Text100
    serial_number: OptionalText100 | None = None
    location: OptionalText100 | None = None
    purchase_date: date | None = None
    warranty_expires_on: date | None = None
    notes: Annotated[str, Field(max_length=5000)] | None = None

    @model_validator(mode="after")
    def dates_in_order(self) -> "AssetCreate":
        _check_dates(self.purchase_date, self.warranty_expires_on)
        return self


class AssetUpdate(BaseModel):
    """Partial update. Status and assignee change through their own endpoints."""

    type: AssetType | None = None
    manufacturer: Text100 | None = None
    model: Text100 | None = None
    serial_number: OptionalText100 | None = None
    location: OptionalText100 | None = None
    purchase_date: date | None = None
    warranty_expires_on: date | None = None
    notes: Annotated[str, Field(max_length=5000)] | None = None

    @model_validator(mode="after")
    def dates_in_order(self) -> "AssetUpdate":
        _check_dates(self.purchase_date, self.warranty_expires_on)
        return self


class AssetStatusChange(BaseModel):
    status: AssetStatus


class AssignmentChange(BaseModel):
    assigned_to_id: int | None


class AssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_tag: str
    type: AssetType
    manufacturer: str
    model: str
    serial_number: str | None
    status: AssetStatus
    assigned_to: UserBrief | None
    location: str | None
    purchase_date: date | None
    warranty_expires_on: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warranty_state(self) -> Literal["active", "expiring", "expired"] | None:
        return warranty_state(self.warranty_expires_on, datetime.now(UTC).date())


class AssetPage(BaseModel):
    items: list[AssetRead]
    total: int


def warranty_state(
    expires_on: date | None, today: date
) -> Literal["active", "expiring", "expired"] | None:
    if expires_on is None:
        return None
    if expires_on < today:
        return "expired"
    if expires_on <= today + timedelta(days=WARRANTY_WARNING_DAYS):
        return "expiring"
    return "active"
