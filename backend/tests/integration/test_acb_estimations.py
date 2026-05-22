"""Integration tests for the ACB estimation path through POST /v1/estimations.

Verifies that when ``estimation_mode='acb'`` is sent in the request body,
the backend routes to ``ai_client.estimate_acb`` and persists the result.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

VALID_TRANSCRIPTION = (
    "A B2B SaaS company needs a multi-tenant billing platform with Stripe "
    "integration, role-based access control, and a real-time reporting dashboard."
)

ACB_AI_RESPONSE = {
    "estimation": "## Billing Platform\n### Phase 1 — Backend: 120h\n**Total: 200h**",
    "model": "gpt-4o-mini",
    "input_tokens": 650,
    "output_tokens": 280,
    "turn_cost_usd": 0.0009,
    "total_cost_usd": 0.0009,
    "requirements": None,
    "validation": {"warnings": []},
    "structured_result": None,
    "prompt_version": "v1",
    # ACB-specific fields (returned by AI Engine but stored as estimation_markdown)
    "iterations": [
        {
            "iteration": 0,
            "candidate_estimate": "draft...",
            "critic_feedback": {"issues": [], "overall_assessment": "OK", "approved": True},
            "boss_decision": {"action": "accept", "reasoning": "approved"},
        }
    ],
    "final_decision": {"action": "accept", "reasoning": "approved"},
    "acb_total_input_tokens": 650,
    "acb_total_output_tokens": 280,
}

STANDARD_AI_RESPONSE = {
    "estimation": "## Standard estimate",
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


def _patch_ai_acb(payload=None):
    return patch(
        "app.services.ai_client.estimate_acb",
        AsyncMock(return_value=payload or ACB_AI_RESPONSE),
    )


def _patch_ai_sync(payload=None):
    return patch(
        "app.services.ai_client.estimate_sync",
        AsyncMock(return_value=payload or STANDARD_AI_RESPONSE),
    )


class TestAcbEstimationIntegration:
    async def test_acb_mode_returns_200(self, client, auth_headers):
        with _patch_ai_acb():
            response = await client.post(
                "/v1/estimations",
                headers=auth_headers,
                json={
                    "transcription": VALID_TRANSCRIPTION,
                    "estimation_mode": "acb",
                    "acb_max_iterations": 1,
                },
            )
        assert response.status_code == 201

    async def test_acb_mode_response_has_estimation_markdown(self, client, auth_headers):
        with _patch_ai_acb():
            response = await client.post(
                "/v1/estimations",
                headers=auth_headers,
                json={
                    "transcription": VALID_TRANSCRIPTION,
                    "estimation_mode": "acb",
                    "acb_max_iterations": 1,
                },
            )
        data = response.json()
        assert "estimation_markdown" in data
        assert data["estimation_markdown"] is not None

    async def test_acb_mode_routes_to_estimate_acb_not_sync(self, client, auth_headers):
        mock_acb = AsyncMock(return_value=ACB_AI_RESPONSE)
        mock_sync = AsyncMock(return_value=STANDARD_AI_RESPONSE)

        with (
            patch("app.services.ai_client.estimate_acb", mock_acb),
            patch("app.services.ai_client.estimate_sync", mock_sync),
        ):
            await client.post(
                "/v1/estimations",
                headers=auth_headers,
                json={
                    "transcription": VALID_TRANSCRIPTION,
                    "estimation_mode": "acb",
                    "acb_max_iterations": 1,
                },
            )

        mock_acb.assert_awaited_once()
        mock_sync.assert_not_awaited()

    async def test_standard_mode_routes_to_estimate_sync(self, client, auth_headers):
        mock_acb = AsyncMock(return_value=ACB_AI_RESPONSE)
        mock_sync = AsyncMock(return_value=STANDARD_AI_RESPONSE)

        with (
            patch("app.services.ai_client.estimate_acb", mock_acb),
            patch("app.services.ai_client.estimate_sync", mock_sync),
        ):
            await client.post(
                "/v1/estimations",
                headers=auth_headers,
                json={"transcription": VALID_TRANSCRIPTION},
            )

        mock_sync.assert_awaited_once()
        mock_acb.assert_not_awaited()

    async def test_acb_max_iterations_above_limit_returns_422(self, client, auth_headers):
        response = await client.post(
            "/v1/estimations",
            headers=auth_headers,
            json={
                "transcription": VALID_TRANSCRIPTION,
                "estimation_mode": "acb",
                "acb_max_iterations": 10,
            },
        )
        assert response.status_code == 422

    async def test_invalid_estimation_mode_returns_422(self, client, auth_headers):
        response = await client.post(
            "/v1/estimations",
            headers=auth_headers,
            json={
                "transcription": VALID_TRANSCRIPTION,
                "estimation_mode": "unknown_mode",
            },
        )
        assert response.status_code == 422
