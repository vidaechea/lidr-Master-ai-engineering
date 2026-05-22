"""FastAPI dependencies for the ai-engine service."""
from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import Depends, Header
from jose import JWTError, jwt

from app.config import settings
from app.schemas.estimation import UserTier

log = structlog.get_logger(__name__)


def get_request_tier(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> UserTier:
    """Extract the user tier from the Bearer JWT claim.

    The tier is embedded by the backend in the access token at login time and
    is never accepted as a free client parameter.  The JWT is verified with the
    shared secret so the claim cannot be tampered with.

    Falls back to UserTier.DEVELOPER when:
    - No Authorization header is present (e.g. internal tooling, tests).
    - The token is invalid or missing the tier claim.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return UserTier.DEVELOPER

    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        raw_tier = payload.get("tier", "developer")
        return UserTier(raw_tier)
    except (JWTError, ValueError):
        log.warning("tier_extraction_failed_fallback_to_developer")
        return UserTier.DEVELOPER


TierDep = Annotated[UserTier, Depends(get_request_tier)]
