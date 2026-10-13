from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ticket import Category, Priority, TicketStatus


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
