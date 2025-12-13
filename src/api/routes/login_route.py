from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from src.api.deps import SessionDep, CurrentUser
from src.core.config import settings
from src.core.security import create_access_token
from src.services.user import (
    Token,
    UserPublic,
    UserRegister,
    authenticate_user,
    create_user,
    get_user_by_email,
    UserCreate,
)

router = APIRouter(tags=["login"])


@router.post("/login/access-token", response_model=Token)
async def login_access_token(
    session: SessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login.
    
    Send email as 'username' and password to get an access token.
    """
    user = await authenticate_user(
        session=session,
        email=form_data.username,
        password=form_data.password
    )
    
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    access_token_expires = timedelta(minutes=settings.access_token_expire_minutes)
    
    return Token(
        access_token=create_access_token(
            subject=str(user.id),
            expires_delta=access_token_expires
        )
    )


@router.post("/login/test-token", response_model=UserPublic)
async def test_token(current_user: CurrentUser) -> UserPublic:
    """
    Test access token validity.
    
    Returns current user if token is valid.
    """
    return UserPublic.model_validate(current_user)


@router.post("/signup", response_model=UserPublic)
async def register_user(
    session: SessionDep,
    user_in: UserRegister
) -> UserPublic:
    """
    Register a new user (public endpoint).
    """
    # Check if user already exists
    existing_user = await get_user_by_email(session, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="A user with this email already exists"
        )
    
    # Create new user
    user = await create_user(
        session=session,
        user_create=UserCreate(
            email=user_in.email,
            password=user_in.password,
            full_name=user_in.full_name,
        )
    )
    
    return UserPublic.model_validate(user)