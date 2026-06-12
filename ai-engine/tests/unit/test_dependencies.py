"""Unit tests for the TierDep FastAPI dependency.

Verifies that the tier is always sourced from the JWT claim and never from
a free client parameter, preventing Anti-pattern #1 (client-controlled tier).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt

from app.dependencies import get_request_tier
from app.domain.schemas.estimation import UserTier

# Shared secret for test tokens — must match what settings.secret_key provides
_SECRET = "test-secret"
_ALGORITHM = "HS256"


def _make_token(tier: str | None = "developer", secret: str = _SECRET, expired: bool = False) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=-1 if expired else 1)
    payload: dict = {"sub": "user-1", "exp": exp}
    if tier is not None:
        payload["tier"] = tier
    return jwt.encode(payload, secret, algorithm=_ALGORITHM)


class TestGetRequestTier:
    """get_request_tier() must extract tier from JWT and never from the request body."""

    def _call(self, authorization: str | None) -> UserTier:
        with (
            patch("app.dependencies.settings.secret_key", _SECRET),
            patch("app.dependencies.settings.algorithm", _ALGORITHM),
        ):
            return get_request_tier(authorization=authorization)

    # ------------------------------------------------------------------
    # Fallback cases — no valid token → developer (minimum privilege)
    # ------------------------------------------------------------------

    def test_returns_developer_when_no_header(self):
        assert self._call(None) == UserTier.DEVELOPER

    def test_returns_developer_when_header_has_no_bearer_prefix(self):
        assert self._call("Token some-value") == UserTier.DEVELOPER

    def test_returns_developer_when_bearer_value_is_empty(self):
        assert self._call("Bearer ") == UserTier.DEVELOPER

    def test_returns_developer_when_jwt_signature_invalid(self):
        token = _make_token("executive", secret="wrong-secret")
        assert self._call(f"Bearer {token}") == UserTier.DEVELOPER

    def test_returns_developer_when_jwt_is_expired(self):
        token = _make_token("pm", expired=True)
        assert self._call(f"Bearer {token}") == UserTier.DEVELOPER

    def test_returns_developer_when_tier_claim_is_missing(self):
        token = _make_token(tier=None)
        assert self._call(f"Bearer {token}") == UserTier.DEVELOPER

    def test_returns_developer_when_tier_claim_is_unknown_value(self):
        token = _make_token(tier="superadmin")
        assert self._call(f"Bearer {token}") == UserTier.DEVELOPER

    # ------------------------------------------------------------------
    # Happy path — valid tokens carry the correct tier
    # ------------------------------------------------------------------

    def test_extracts_developer_tier_from_jwt(self):
        token = _make_token("developer")
        assert self._call(f"Bearer {token}") == UserTier.DEVELOPER

    def test_extracts_pm_tier_from_jwt(self):
        token = _make_token("pm")
        assert self._call(f"Bearer {token}") == UserTier.PM

    def test_extracts_executive_tier_from_jwt(self):
        token = _make_token("executive")
        assert self._call(f"Bearer {token}") == UserTier.EXECUTIVE

    # ------------------------------------------------------------------
    # Anti-pattern guard — tier is never in the request body
    # ------------------------------------------------------------------

    def test_estimation_request_has_no_tier_field(self):
        """EstimationRequest must not expose a tier field — prevents client injection."""
        from app.domain.schemas.estimation import EstimationRequest
        fields = EstimationRequest.model_fields
        assert "tier" not in fields, (
            "EstimationRequest must NOT contain a 'tier' field. "
            "Tier must come exclusively from the JWT claim."
        )

