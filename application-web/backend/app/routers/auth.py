from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.dependencies import DbDep, CurrentUser
from app.models.user import User
from app.schemas.auth import RegisterRequest, TokenResponse, RefreshRequest
from app.schemas.user import UserOut, UserUpdate
from app.services.auth_service import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: DbDep):
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, tier=user.tier),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/login", response_model=TokenResponse)
async def login(db: DbDep, form: OAuth2PasswordRequestForm = Depends()):
    result = await db.execute(select(User).where(User.email == form.username))
    user = result.scalar_one_or_none()
    if not user or not user.hashed_password or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    user_id = str(user.id)
    return TokenResponse(
        access_token=create_access_token(user_id, tier=user.tier),
        refresh_token=create_refresh_token(user_id),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(body: RefreshRequest, db: DbDep):
    try:
        user_id = decode_refresh_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return TokenResponse(
        access_token=create_access_token(user_id, tier=user.tier),
        refresh_token=create_refresh_token(user_id),
    )


@router.get("/me", response_model=UserOut)
async def get_me(current_user: CurrentUser):
    return current_user


@router.patch("/me", response_model=UserOut)
async def update_me(body: UserUpdate, current_user: CurrentUser, db: DbDep):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(current_user, field, value)
    await db.commit()
    await db.refresh(current_user)
    return current_user
