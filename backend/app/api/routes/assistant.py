from functools import lru_cache
from typing import Annotated

from anthropic import AsyncAnthropic
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.access import STAFF_ROLES, load_ticket
from app.api.deps import SessionDep, require_roles
from app.core.config import Settings, get_settings
from app.core.ratelimit import LimiterDep
from app.models.user import User
from app.schemas.assistant import AssistantReply, AssistantSource
from app.services import articles as search
from app.services import assistant, audit

router = APIRouter(prefix="/tickets", tags=["assistant"])

StaffUser = Annotated[User, Depends(require_roles(*STAFF_ROLES))]


@lru_cache
def get_client() -> AsyncAnthropic | None:
    """The model client, or None when no API key is configured. Overridden in tests."""
    return assistant.make_client(get_settings())


ClientDep = Annotated[AsyncAnthropic | None, Depends(get_client)]


def _no_answer(reason: str) -> AssistantReply:
    return AssistantReply(answer=None, sources=[], reason=reason)


@router.post("/{ticket_id}/assistant")
async def ask_assistant(
    ticket_id: int,
    session: SessionDep,
    user: StaffUser,
    client: ClientDep,
    limiter: LimiterDep,
) -> AssistantReply:
    """Suggest troubleshooting steps for a ticket from published knowledge-base articles."""
    settings: Settings = get_settings()
    if client is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The assistant is not configured")
    ticket = await load_ticket(session, ticket_id, user)

    found = await search.find_relevant(
        session, f"{ticket.title} {ticket.description}"[:400], assistant.MAX_ARTICLES
    )
    articles = [a for a, _ in found]
    if not articles:
        return _no_answer("no_articles")  # nothing to ground on, so don't pay for a model call

    # Counted before the call: a failing or slow request still costs, so it still counts.
    key = f"assistant:{user.id}"
    used, wait = await limiter.state(key)
    if used >= settings.assistant_max_requests:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Assistant limit reached. Try again in {max(wait // 60, 1)} minutes.",
            headers={"Retry-After": str(wait)},
        )
    await limiter.record(key, settings.assistant_window_seconds)

    try:
        result = await assistant.suggest(client, settings, ticket, articles)
    except assistant.AssistantUnavailable:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The assistant could not answer right now"
        ) from None

    audit.record(
        session,
        user,
        "ticket",
        ticket.id,
        "assistant_suggested",
        {
            "model": settings.assistant_model,
            "retrieved": [a.id for a in articles],
            "cited": [a.id for a in result[1]] if result else [],
        },
    )
    await session.commit()  # the session does not commit by itself
    if result is None:
        return _no_answer("not_covered")
    steps, cited = result
    return AssistantReply(
        answer=steps,
        sources=[AssistantSource(id=a.id, title=a.title) for a in cited],
    )
