from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import get_settings
from app.core.ratelimit import LimiterDep, RateLimiter
from app.core.security import create_token, decode_token, verify_password
from app.models.user import User
from app.schemas.auth import RefreshRequest, TokenPair
from app.schemas.user import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def _issue_tokens(user: User) -> TokenPair:
    subject = str(user.id)
    return TokenPair(
        access_token=create_token(subject, "access"),
        refresh_token=create_token(subject, "refresh"),
    )


async def _retry_after_if_locked(limiter: RateLimiter, person_key: str, ip_key: str) -> int | None:
    settings = get_settings()
    for key, limit in (
        (person_key, settings.login_max_failures),
        (ip_key, settings.login_max_failures_per_ip),
    ):
        failures, ttl = await limiter.state(key)
        if failures >= limit:
            return max(ttl, 1)
    return None


@router.post("/login")
async def login(
    request: Request,
    session: SessionDep,
    limiter: LimiterDep,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenPair:
    settings = get_settings()
    email = form.username.lower()
    ip = request.client.host if request.client else "unknown"
    # The person's key includes the address, so someone elsewhere cannot lock them out by guessing.
    person_key, ip_key = f"login:fail:{ip}:{email}", f"login:fail-ip:{ip}"

    # Checked before the password is, so a locked-out caller learns nothing about whether a guess
    # was right, or whether the account exists.
    if (wait := await _retry_after_if_locked(limiter, person_key, ip_key)) is not None:
        minutes = -(-wait // 60)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many failed sign-in attempts. Try again in {minutes} minute"
            f"{'s' if minutes != 1 else ''}.",
            headers={"Retry-After": str(wait)},
        )

    user = await session.scalar(select(User).where(User.email == email))
    if (
        user is None
        or not user.is_active
        or not verify_password(form.password, user.hashed_password)
    ):
        await limiter.record(person_key, settings.login_window_seconds)
        await limiter.record(ip_key, settings.login_window_seconds)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")

    await limiter.reset(person_key)
    return _issue_tokens(user)


@router.post("/refresh")
async def refresh(session: SessionDep, body: RefreshRequest) -> TokenPair:
    try:
        user_id = int(decode_token(body.refresh_token, "refresh"))
    except (jwt.InvalidTokenError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token") from None
    user = await session.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    return _issue_tokens(user)


@router.get("/me")
async def me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)
