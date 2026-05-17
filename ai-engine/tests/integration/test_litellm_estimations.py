"""Integration tests for the /estimate endpoint when llm_provider="litellm".

These tests verify that the full FastAPI→LiteLLMRouterService pipeline
produces the same response contract as the OpenAI and Anthropic providers,
without coupling to any specific upstream HTTP call.

The litellm.Router is mocked at construction time so no real API keys are needed.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

VALID_TRANSCRIPTION = "Build an e-commerce platform with user auth and product catalog."

FAKE_OUTPUT = (
    "## Estimate: E-commerce Platform\n\n"
    "1. UI/UX Design: 40 hours\n"
    "2. Backend API: 60 hours\n\n"
    "**Total: 100 hours**"
)
FAKE_RESPONSE_ID = "chatcmpl-litellm-001"
FAKE_REQUIREMENTS = (
    "1. User authentication with JWT\n"
    "2. Product catalog with search and filtering\n"
    "3. Shopping cart and checkout flow\n"
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _make_litellm_response(
    content: str = FAKE_OUTPUT,
    response_id: str = FAKE_RESPONSE_ID,
    prompt_tokens: int = 600,
    completion_tokens: int = 250,
    finish_reason: str = "stop",
) -> MagicMock:
    """Build a minimal mock that mimics a litellm / OpenAI Chat Completions response."""
    response = MagicMock()
    response.id = response_id
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    response.choices[0].finish_reason = finish_reason
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    return response


def _patch_litellm_router(mock_response: MagicMock):
    """Patch the litellm_router_service singleton's internal router.

    Replaces the already-instantiated singleton's _router so that any
    acompletion call returns mock_response without hitting real APIs.
    """
    import app.services.litellm_service as _svc

    mock_router = MagicMock()
    mock_router.acompletion = AsyncMock(return_value=mock_response)
    mock_router.model_list = [
        {"model_name": "estimator", "litellm_params": {"model": "gpt-4o-mini"}},
        {"model_name": "estimator", "litellm_params": {"model": "anthropic/claude-haiku-4-5-20251001"}},
    ]
    return patch.object(_svc.litellm_router_service, "_router", mock_router)


@pytest.fixture()
def litellm_client(monkeypatch) -> TestClient:
    """Test client with llm_provider forced to 'litellm'."""
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "llm_provider", "litellm")
    return TestClient(app)


# --------------------------------------------------------------------------- #
# GET /api/v1/examples — should be unaffected by provider
# --------------------------------------------------------------------------- #


class TestExamplesEndpointUnaffected:
    def test_returns_200_regardless_of_provider(self, litellm_client: TestClient):
        response = litellm_client.get("/api/v1/examples")
        assert response.status_code == 200


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — success path
# --------------------------------------------------------------------------- #


class TestCreateEstimationLiteLLM:
    def test_returns_200_with_valid_payload(self, litellm_client: TestClient):
        mock_response = _make_litellm_response()
        with _patch_litellm_router(mock_response):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 200

    def test_estimation_value_matches_router_output(self, litellm_client: TestClient):
        mock_response = _make_litellm_response(content=FAKE_OUTPUT)
        with _patch_litellm_router(mock_response):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.json()["estimation"] == FAKE_OUTPUT

    def test_response_shape_matches_openai_provider_contract(self, litellm_client: TestClient):
        """litellm provider must return the same fields as openai/anthropic providers."""
        mock_response = _make_litellm_response()
        with _patch_litellm_router(mock_response):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        for field in (
            "estimation",
            "model",
            "input_tokens",
            "output_tokens",
            "turn_cost_usd",
            "total_cost_usd",
            "response_id",
            "estimated_input_tokens",
            "estimated_precall_cost_usd",
        ):
            assert field in data, f"Missing field: {field}"

    def test_response_id_matches_mock(self, litellm_client: TestClient):
        mock_response = _make_litellm_response(response_id=FAKE_RESPONSE_ID)
        with _patch_litellm_router(mock_response):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.json()["response_id"] == FAKE_RESPONSE_ID

    def test_token_counts_match_mock_usage(self, litellm_client: TestClient):
        mock_response = _make_litellm_response(prompt_tokens=600, completion_tokens=250)
        with _patch_litellm_router(mock_response):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert data["input_tokens"] == 600
        assert data["output_tokens"] == 250

    def test_returns_422_when_transcription_too_short(self, litellm_client: TestClient):
        response = litellm_client.post("/api/v1/estimate", json={"transcription": "Too short."})
        assert response.status_code == 422

    def test_returns_422_when_transcription_missing(self, litellm_client: TestClient):
        response = litellm_client.post("/api/v1/estimate", json={})
        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — pre-call two-step flow
# --------------------------------------------------------------------------- #


class TestCreateEstimationLiteLLMPreCall:
    def _pre_call_mock(self) -> MagicMock:
        return _make_litellm_response(
            content=FAKE_REQUIREMENTS,
            response_id="chatcmpl-pre",
            prompt_tokens=300,
            completion_tokens=80,
        )

    def _estimation_mock(self) -> MagicMock:
        return _make_litellm_response(
            content=FAKE_OUTPUT,
            response_id="chatcmpl-est",
            prompt_tokens=400,
            completion_tokens=200,
        )

    def _patch_two_calls(self, litellm_client: TestClient):
        import app.services.litellm_service as _svc

        pre = self._pre_call_mock()
        est = self._estimation_mock()
        mock_router = MagicMock()
        mock_router.acompletion = AsyncMock(side_effect=[pre, est])
        mock_router.model_list = [
            {"model_name": "estimator", "litellm_params": {"model": "gpt-4o-mini"}},
            {"model_name": "estimator", "litellm_params": {"model": "anthropic/claude-haiku-4-5-20251001"}},
        ]
        return patch.object(_svc.litellm_router_service, "_router", mock_router), mock_router

    def test_returns_200_with_pre_call_enabled(self, litellm_client: TestClient):
        ctx, _ = self._patch_two_calls(litellm_client)
        with ctx:
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.status_code == 200

    def test_requirements_field_populated_when_pre_call_enabled(self, litellm_client: TestClient):
        ctx, _ = self._patch_two_calls(litellm_client)
        with ctx:
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.json()["requirements"] == FAKE_REQUIREMENTS

    def test_estimation_field_contains_main_call_output(self, litellm_client: TestClient):
        ctx, _ = self._patch_two_calls(litellm_client)
        with ctx:
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.json()["estimation"] == FAKE_OUTPUT

    def test_router_called_twice_for_pre_call_flow(self, litellm_client: TestClient):
        ctx, mock_router = self._patch_two_calls(litellm_client)
        with ctx:
            litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert mock_router.acompletion.call_count == 2

    def test_pre_call_cost_is_positive(self, litellm_client: TestClient):
        ctx, _ = self._patch_two_calls(litellm_client)
        with ctx:
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.json()["pre_call_cost_usd"] > 0

    def test_pre_call_cost_is_none_when_disabled(self, litellm_client: TestClient):
        mock_response = _make_litellm_response()
        with _patch_litellm_router(mock_response):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": False},
            )
        assert response.json()["pre_call_cost_usd"] is None


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — error propagation
# --------------------------------------------------------------------------- #


class TestCreateEstimationLiteLLMErrors:
    def test_returns_413_on_context_overflow(self, litellm_client: TestClient):
        from app.services.helpers.prompt_builder import PromptBuilder
        from app.services.helpers.error_mapper import LLMServiceError

        # Patch validate_context_window to raise context overflow error
        def raise_overflow(*args, **kwargs):
            raise LLMServiceError(
                "context_overflow",
                "Estimated request size exceeds context window.",
                413,
            )

        mock_response = _make_litellm_response()
        with _patch_litellm_router(mock_response):
            with patch.object(PromptBuilder, "validate_context_window", side_effect=raise_overflow):
                response = litellm_client.post(
                    "/api/v1/estimate",
                    json={"transcription": VALID_TRANSCRIPTION},
                )
        assert response.status_code == 413

    def test_returns_401_on_auth_error(self, litellm_client: TestClient):
        import litellm as _litellm
        import app.services.litellm_service as _svc

        mock_router = MagicMock()
        mock_router.acompletion = AsyncMock(
            side_effect=_litellm.AuthenticationError(
                message="Invalid key", llm_provider="openai", model="gpt-4o-mini"
            )
        )
        with patch.object(_svc.litellm_router_service, "_router", mock_router):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 401

    def test_returns_429_on_rate_limit(self, litellm_client: TestClient):
        import litellm as _litellm
        import app.services.litellm_service as _svc

        mock_router = MagicMock()
        mock_router.acompletion = AsyncMock(
            side_effect=_litellm.RateLimitError(
                message="Rate limit", llm_provider="openai", model="gpt-4o-mini"
            )
        )
        with patch.object(_svc.litellm_router_service, "_router", mock_router):
            response = litellm_client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 429


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate/structured — output guardrail (scope filter + validation)
# --------------------------------------------------------------------------- #

def _make_struct_completion(finish_reason: str = "stop") -> MagicMock:
    comp = MagicMock()
    comp.id = "resp-struct-integration-001"
    comp.choices = [MagicMock()]
    comp.choices[0].finish_reason = finish_reason
    comp.usage = MagicMock()
    comp.usage.prompt_tokens = 400
    comp.usage.completion_tokens = 150
    return comp


def _patch_complete_structured(mock_result, mock_completion):
    return patch(
        "app.services.litellm_service.LiteLLMRouterService.complete_structured",
        AsyncMock(return_value=(mock_result, mock_completion)),
    )


class TestStructuredOutputGuardrail:
    """Verify that both output guardrail layers run on POST /estimate/structured."""

    def _normal_result(self):
        from app.schemas.estimation import EstimationResult, Phase
        phase = Phase(name="Backend", duration_weeks=2, cost_eur=5_000, confidence_pct=80)
        return EstimationResult(
            summary="E-commerce platform",
            confidence_pct=80,
            phases=[phase],
            total_duration_weeks=2,
            total_cost_eur=5_000,
        )

    def _low_confidence_result(self):
        from app.schemas.estimation import EstimationResult, Phase
        phase = Phase(name="Unknown scope", duration_weeks=1, cost_eur=0, confidence_pct=10)
        return EstimationResult(
            summary="I cannot estimate this without more information",
            confidence_pct=10,
            phases=[phase],
            total_duration_weeks=1,
            total_cost_eur=0,
        )

    def test_structured_endpoint_returns_200(self, client: TestClient):
        comp = _make_struct_completion()
        with _patch_complete_structured(self._normal_result(), comp):
            response = client.post(
                "/api/v1/estimate/structured",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 200

    def test_validation_always_present_in_structured_response(self, client: TestClient):
        comp = _make_struct_completion()
        with _patch_complete_structured(self._normal_result(), comp):
            response = client.post(
                "/api/v1/estimate/structured",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert data["validation"] is not None
        assert "score" in data["validation"]
        assert "issues" in data["validation"]

    def test_scope_filter_rewrites_low_confidence_summary(self, client: TestClient):
        comp = _make_struct_completion()
        with _patch_complete_structured(self._low_confidence_result(), comp):
            response = client.post(
                "/api/v1/estimate/structured",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["estimation"].startswith("## Out of scope:")

    def test_scope_filter_zeroes_cost_in_structured_result(self, client: TestClient):
        comp = _make_struct_completion()
        with _patch_complete_structured(self._low_confidence_result(), comp):
            response = client.post(
                "/api/v1/estimate/structured",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        structured = response.json()["structured_result"]
        assert structured["total_cost_eur"] == 0

    def test_high_confidence_result_not_rewritten(self, client: TestClient):
        comp = _make_struct_completion()
        with _patch_complete_structured(self._normal_result(), comp):
            response = client.post(
                "/api/v1/estimate/structured",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert not data["estimation"].startswith("## Out of scope:")
        assert data["structured_result"]["total_cost_eur"] == 5_000
