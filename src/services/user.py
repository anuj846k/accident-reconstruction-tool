import uuid
from typing import Optional
from datetime import datetime

from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.core.security import get_password_hash, verify_password


# --- Pydantic Schemas ---

class UserCreate(BaseModel):
    """Schema for creating a new user."""
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserRegister(BaseModel):
    """Schema for user registration (public signup)."""
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserPublic(BaseModel):
    """Schema for returning user data (no password)."""
    id: uuid.UUID
    email: str
    full_name: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    """Schema for JWT token response."""
    access_token: str
    token_type: str = "bearer"


class Message(BaseModel):
    """Generic message response."""
    message: str


# --- CRUD Functions ---

async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    """Get user by email address."""
    result = await session.execute(
        select(User).where(User.email == email)
    )
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, user_create: UserCreate) -> User:
    """Create a new user with hashed password."""
    user = User(
        email=user_create.email,
        hashed_password=get_password_hash(user_create.password),
        full_name=user_create.full_name,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def authenticate_user(
    session: AsyncSession, email: str, password: str
) -> Optional[User]:
    """Verify email and password, return user if valid."""
    user = await get_user_by_email(session, email)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user