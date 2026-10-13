from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import Role


class UserBase(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=200)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.REQUESTER


class UserRead(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Role
    is_active: bool
    created_at: datetime
