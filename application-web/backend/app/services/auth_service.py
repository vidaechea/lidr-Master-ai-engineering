from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(data: dict, expires_delta: timedelta) -> str:
    payload = {**data, "exp": datetime.now(timezone.utc) + expires_delta}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def create_access_token(user_id: str, tier: str = "developer") -> str:
    return _create_token(
        {"sub": user_id, "type": "access", "tier": tier},
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
