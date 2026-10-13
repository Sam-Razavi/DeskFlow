from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models.article import ArticleStatus
from app.models.ticket import Category
from app.schemas.ticket import UserBrief

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
Body = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50_000)]


class ArticleCreate(BaseModel):
    title: Title
    body: Body
    category: Category = Category.OTHER


class ArticleUpdate(BaseModel):
    title: Title | None = None
    body: Body | None = None
    category: Category | None = None


class ArticleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    category: Category
    status: ArticleStatus
    author: UserBrief
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ArticleSummary(BaseModel):
    id: int
    title: str
    category: Category
    status: ArticleStatus
    author: UserBrief
    published_at: datetime | None
    updated_at: datetime
    # For a search, a fragment of the body around the match with the matched words wrapped in the
    # HIGHLIGHT_START / HIGHLIGHT_END characters; otherwise the start of the article as plain text.
    snippet: Annotated[str, Field(max_length=1000)]


class ArticlePage(BaseModel):
    items: list[ArticleSummary]
    total: int
