"""Unit tests for the ACB dispatch path in create_and_run_sync.

Verifies that ``create_and_run_sync`` calls ``ai_client.estimate_acb`` (not
``estimate_sync``) when ``estimation_mode='acb'``, and that it correctly maps
``acb_max_iterations`` → ``max_iterations`` in the AI Engine payload.
"""
from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.estimation import EstimationCreate
from app.services.estimation_service import create_and_run_sync

_USER_ID = uuid.uuid4()

_ACB_PAYLOAD = EstimationCreate(
    transcription=(
        "Build a multi-tenant SaaS billing platform with Stripe integration "
        "and a real-time reporting dashboard."
    ),
    estimation_mode="acb",
    acb_max_iterations=1,
)

_STANDARD_PAYLOAD = EstimationCreate(
    transcription=(
        "Build a multi-tenant SaaS billing platform with Stripe integration "
        "and a real-time reporting dashboard."
    ),
    estimation_mode="standard",
)

_FAKE_AI_RESPONSE = {
    "estimation": "## Estimate\nTotal: 200 h",
    "model": "gpt-4o-mini",
    "input_tokens": 400,
    "output_tokens": 150,
    "turn_cost_usd": 0.0005,
    "total_cost_usd": 0.0005,
    "requirements": None,
    "validation": None,
    "structured_result": None,
    "prompt_version": "v1",
}


def _make_db_mock():
    db = AsyncMock()
    estimation = MagicMock()
    estimation.id = uuid.uuid4()
    estimation.status = "processing"
    estimation.error_detail = None
    estimation.estimation_markdown = None
    # db.refresh sets the estimation fields from the mock response
    db.refresh = AsyncMock()
    db.add = MagicMock()
    return db, estimation


class TestAcbDispatch:
    async def test_acb_mode_calls_estimate_acb(self):
        """estimation_mode='acb' must route to ai_client.estimate_acb."""
        db, _ = _make_db_mock()
        mock_acb = AsyncMock(return_value=_FAKE_AI_RESPONSE)
        mock_sync = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with (
            patch("app.services.estimation_service.ai_client.estimate_acb", mock_acb),
            patch("app.services.estimation_service.ai_client.estimate_sync", mock_sync),
        ):
            await create_and_run_sync(db, _USER_ID, _ACB_PAYLOAD)

        mock_acb.assert_awaited_once()
        mock_sync.assert_not_awaited()

    async def test_standard_mode_calls_estimate_sync(self):
        """estimation_mode='standard' must route to ai_client.estimate_sync."""
        db, _ = _make_db_mock()
        mock_acb = AsyncMock(return_value=_FAKE_AI_RESPONSE)
        mock_sync = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with (
            patch("app.services.estimation_service.ai_client.estimate_acb", mock_acb),
            patch("app.services.estimation_service.ai_client.estimate_sync", mock_sync),
        ):
            await create_and_run_sync(db, _USER_ID, _STANDARD_PAYLOAD)

        mock_sync.assert_awaited_once()
        mock_acb.assert_not_awaited()

    async def test_acb_payload_includes_max_iterations(self):
        """acb_max_iterations is mapped to max_iterations in the ACB payload."""
        db, _ = _make_db_mock()
        mock_acb = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with patch("app.services.estimation_service.ai_client.estimate_acb", mock_acb):
            with patch("app.services.estimation_service.ai_client.estimate_sync", AsyncMock()):
                await create_and_run_sync(db, _USER_ID, _ACB_PAYLOAD)

        call_payload = mock_acb.call_args[0][0]
        assert call_payload["max_iterations"] == _ACB_PAYLOAD.acb_max_iterations

    async def test_acb_payload_excludes_backend_only_fields(self):
        """estimation_mode and acb_max_iterations must not be forwarded to AI Engine."""
        db, _ = _make_db_mock()
        mock_acb = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with patch("app.services.estimation_service.ai_client.estimate_acb", mock_acb):
            with patch("app.services.estimation_service.ai_client.estimate_sync", AsyncMock()):
                await create_and_run_sync(db, _USER_ID, _ACB_PAYLOAD)

        call_payload = mock_acb.call_args[0][0]
        assert "estimation_mode" not in call_payload
        assert "acb_max_iterations" not in call_payload
        assert "prompt_version" not in call_payload

    async def test_standard_payload_excludes_backend_only_fields(self):
        """estimation_mode and acb_max_iterations must not be forwarded in standard mode."""
        db, _ = _make_db_mock()
        mock_sync = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with patch("app.services.estimation_service.ai_client.estimate_sync", mock_sync):
            with patch("app.services.estimation_service.ai_client.estimate_acb", AsyncMock()):
                await create_and_run_sync(db, _USER_ID, _STANDARD_PAYLOAD)

        call_payload = mock_sync.call_args[0][0]
        assert "estimation_mode" not in call_payload
        assert "acb_max_iterations" not in call_payload
        assert "prompt_version" not in call_payload

    async def test_acb_mode_passes_prompt_version_as_explicit_argument(self):
        """ACB mode forwards prompt_version separately from the JSON payload."""
        db, _ = _make_db_mock()
        mock_acb = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with patch("app.services.estimation_service.ai_client.estimate_acb", mock_acb):
            with patch("app.services.estimation_service.ai_client.estimate_sync", AsyncMock()):
                await create_and_run_sync(db, _USER_ID, _ACB_PAYLOAD)

        assert mock_acb.call_args.kwargs["prompt_version"] == _ACB_PAYLOAD.prompt_version

    async def test_standard_mode_passes_prompt_version_as_explicit_argument(self):
        """Standard mode forwards prompt_version separately from the JSON payload."""
        db, _ = _make_db_mock()
        mock_sync = AsyncMock(return_value=_FAKE_AI_RESPONSE)

        with patch("app.services.estimation_service.ai_client.estimate_sync", mock_sync):
            with patch("app.services.estimation_service.ai_client.estimate_acb", AsyncMock()):
                await create_and_run_sync(db, _USER_ID, _STANDARD_PAYLOAD)

        assert mock_sync.call_args.kwargs["prompt_version"] == _STANDARD_PAYLOAD.prompt_version
