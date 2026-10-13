from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import SessionDep, require_roles
from app.core.security import hash_password
from app.models.user import Role, User
from app.schemas.user import UserCreate, UserRead

router = APIRouter(prefix="/users", tags=["users"])

AdminUser = Annotated[User, Depends(require_roles(Role.ADMIN))]
StaffUser = Annotated[User, Depends(require_roles(Role.AGENT, Role.ADMIN))]


@router.get("")
async def list_users(session: SessionDep, _: StaffUser) -> list[UserRead]:
    users = await session.scalars(select(User).order_by(User.full_name))
    return [UserRead.model_validate(u) for u in users]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(session: SessionDep, _: AdminUser, body: UserCreate) -> UserRead:
    email = body.email.lower()
    if await session.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(
        email=email,
        full_name=body.full_name,
        hashed_password=hash_password(body.password),
        role=body.role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return UserRead.model_validate(user)
