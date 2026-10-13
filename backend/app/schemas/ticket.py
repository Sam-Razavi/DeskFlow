from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.models.ticket import Category, Priority, TicketStatus
from app.services import sla
from app.services.sla import SlaState


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str


class TicketCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    priority: Priority = Priority.P3
    category: Category = Category.OTHER
    # Staff may log a ticket on behalf of someone else; ignored for requesters.
    requester_id: int | None = None


class TicketUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, min_length=1, max_length=10_000)
    priority: Priority | None = None
    category: Category | None = None


class StatusChange(BaseModel):
    status: TicketStatus


class AssigneeChange(BaseModel):
    assignee_id: int | None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: str
    status: TicketStatus
    priority: Priority
    category: Category
    requester: UserBrief
    assignee: UserBrief | None
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    first_response_at: datetime | None
    response_due_at: datetime
    resolution_due_at: datetime
    sla_paused_at: datetime | None

    # The states are derived from the fields above at request time, so they are never stale.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def response_sla(self) -> SlaState:
        return sla.response_state(self, sla.utcnow())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def resolution_sla(self) -> SlaState:
        return sla.resolution_state(self, sla.utcnow())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def sla_state(self) -> SlaState:
        return sla.overall_state(self, sla.utcnow())


class TicketPage(BaseModel):
    items: list[TicketRead]
    total: int


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)
    is_internal: bool = False


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    author: UserBrief
    body: str
    is_internal: bool
    created_at: datetime
