from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.access import STAFF_ROLES, is_staff
from app.api.deps import CurrentUser, SessionDep, require_roles
from app.models.article import Article, ArticleStatus
from app.models.audit import AuditLog
from app.models.ticket import Category
from app.models.user import Role, User
from app.schemas.article import (
    ArticleCreate,
    ArticlePage,
    ArticleRead,
    ArticleSummary,
    ArticleUpdate,
)
from app.schemas.audit import AuditLogRead
from app.services import articles as search
from app.services import audit, sla

router = APIRouter(prefix="/articles", tags=["knowledge base"])

StaffUser = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


def _summary(article: Article, snippet: str) -> ArticleSummary:
    return ArticleSummary(
        id=article.id,
        title=article.title,
        category=article.category,
        status=article.status,
        author=article.author,
        published_at=article.published_at,
        updated_at=article.updated_at,
        snippet=snippet,
    )


async def _get_article(session: AsyncSession, article_id: int, user: User) -> Article:
    article = await session.get(Article, article_id)
    # Drafts are staff-only; to anyone else they simply do not exist.
    if article is None or (not is_staff(user) and article.status != ArticleStatus.PUBLISHED):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Article not found")
    return article


@router.get("")
async def list_articles(
    session: SessionDep,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=200)] = None,
    category: Category | None = None,
    status_: Annotated[ArticleStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ArticlePage:
    q = (q or "").strip() or None
    where = []
    if not is_staff(user):
        where.append(Article.status == ArticleStatus.PUBLISHED)
    elif status_:
        where.append(Article.status == status_)
    if category:
        where.append(Article.category == category)

    snippet_col: Any
    order: tuple[Any, ...]
    if q:
        query = search.search_query(q)
        where.append(Article.search_vector.op("@@")(query))
        snippet_col = search.headline(query)
        # Best match first; most recently touched as the tie-break.
        order = (search.rank(query).desc(), Article.updated_at.desc(), Article.id.desc())
    else:
        snippet_col = Article.body  # reduced to a plain-text excerpt below
        order = (
            Article.published_at.desc().nulls_last(),
            Article.updated_at.desc(),
            Article.id.desc(),
        )

    total = await session.scalar(select(func.count()).select_from(Article).where(*where)) or 0
    rows = await session.execute(
        select(Article, snippet_col).where(*where).order_by(*order).limit(limit).offset(offset)
    )
    items = [_summary(a, snippet if q else search.excerpt(snippet)) for a, snippet in rows]
    return ArticlePage(items=items, total=total)


@router.get("/suggest")
async def suggest_articles(
    session: SessionDep,
    _: CurrentUser,
    q: Annotated[str, Query(min_length=2, max_length=200)],
    limit: Annotated[int, Query(ge=1, le=10)] = 5,
) -> list[ArticleSummary]:
    """Published articles that might answer a ticket, from its title or description.

    Open to everyone signed in: this is the self-service step before someone files a ticket.

    Articles containing every word come first. Only if there are none does it fall back to
    articles containing *any* word, keeping just those close in quality to the best of them.
    """
    tiers = (
        (search.all_words_query(q), 0.0),
        (search.suggestion_query(q), search.LENIENT_RELATIVE_CUTOFF),
    )
    for query, cutoff in tiers:
        score = search.rank(query, search.NORMALISE_BY_LENGTH)
        rows = (
            await session.execute(
                select(Article, search.headline(query), score)
                .where(
                    Article.status == ArticleStatus.PUBLISHED,
                    Article.search_vector.op("@@")(query),
                )
                .order_by(score.desc(), Article.updated_at.desc())
                .limit(limit)
            )
        ).all()
        if rows:
            best = rows[0][2]
            return [_summary(a, snippet) for a, snippet, rank in rows if rank >= best * cutoff]
    return []


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_article(session: SessionDep, user: StaffUser, body: ArticleCreate) -> ArticleRead:
    article = Article(
        title=body.title,
        body=body.body,
        category=body.category,
        status=ArticleStatus.DRAFT,
        author_id=user.id,
    )
    session.add(article)
    await session.flush()
    audit.record(
        session,
        user,
        "article",
        article.id,
        "created",
        {"title": article.title, "category": article.category, "status": article.status},
    )
    await session.commit()
    await session.refresh(article)
    return ArticleRead.model_validate(article)


@router.get("/{article_id}")
async def read_article(session: SessionDep, user: CurrentUser, article_id: int) -> ArticleRead:
    return ArticleRead.model_validate(await _get_article(session, article_id, user))


@router.patch("/{article_id}")
async def update_article(
    session: SessionDep, user: StaffUser, article_id: int, body: ArticleUpdate
) -> ArticleRead:
    article = await _get_article(session, article_id, user)
    updates = body.model_dump(exclude_unset=True, exclude_none=True)

    before = {"title": article.title, "category": article.category}
    body_changed = "body" in updates and updates["body"] != article.body
    for field, value in updates.items():
        setattr(article, field, value)

    changes: dict[str, Any] = audit.diff(before, {f: getattr(article, f) for f in before})
    if body_changed:
        # Article bodies can be long; the log records that the text changed, not both copies.
        changes["body_changed"] = True
    if changes:
        audit.record(session, user, "article", article.id, "updated", changes)
    await session.commit()
    await session.refresh(article)
    return ArticleRead.model_validate(article)


async def _set_status(
    session: AsyncSession, user: User, article: Article, target: ArticleStatus, action: str
) -> ArticleRead:
    if article.status == target:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Article is already {target}")
    published_at: datetime | None = sla.utcnow() if target == ArticleStatus.PUBLISHED else None
    audit.record(
        session,
        user,
        "article",
        article.id,
        action,
        {"status": [article.status, target]},
    )
    article.status = target
    article.published_at = published_at
    await session.commit()
    await session.refresh(article)
    return ArticleRead.model_validate(article)


@router.post("/{article_id}/publish")
async def publish_article(session: SessionDep, user: StaffUser, article_id: int) -> ArticleRead:
    article = await _get_article(session, article_id, user)
    return await _set_status(session, user, article, ArticleStatus.PUBLISHED, "published")


@router.post("/{article_id}/unpublish")
async def unpublish_article(session: SessionDep, user: StaffUser, article_id: int) -> ArticleRead:
    article = await _get_article(session, article_id, user)
    return await _set_status(session, user, article, ArticleStatus.DRAFT, "unpublished")


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_article(session: SessionDep, user: StaffUser, article_id: int) -> Response:
    article = await _get_article(session, article_id, user)
    # Staff can discard their own drafts freely; taking down something live is an admin decision.
    if article.status == ArticleStatus.PUBLISHED and user.role != Role.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only an admin can delete a published article"
        )
    audit.record(
        session,
        user,
        "article",
        article.id,
        "deleted",
        {"title": article.title, "status": article.status},
    )
    await session.delete(article)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{article_id}/history")
async def article_history(
    session: SessionDep, user: StaffUser, article_id: int
) -> list[AuditLogRead]:
    await _get_article(session, article_id, user)
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.entity_type == "article", AuditLog.entity_id == article_id)
        .order_by(AuditLog.created_at, AuditLog.id)
    )
    return [AuditLogRead.model_validate(r) for r in rows]
