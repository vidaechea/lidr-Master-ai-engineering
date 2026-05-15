from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = {**data, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "access"},
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(days=settings.refresh_token_expire_days),
    )


def decode_refresh_token(token: str) -> str:
    """Return user_id (sub) from a valid refresh token, raise ValueError otherwise."""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        if payload.get("type") != "refresh":
            raise ValueError("Not a refresh token")
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise ValueError("Missing sub claim")
        return user_id
    except JWTError as exc:
        raise ValueError("Invalid or expired refresh token") from exc


async def get_or_create_oauth_user(
    db: AsyncSession,
    *,
    email: str,
    full_name: str | None,
    provider: str,
    provider_id: str,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            oauth_provider=provider,
            oauth_provider_id=provider_id,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user
