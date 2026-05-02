from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.context.examples import ESTIMATION_EXAMPLES

FAKE_OUTPUT = (
    "## Estimate: E-commerce Platform\n\n"
    "1. UI/UX Design: 40 hours\n"
    "2. Backend API: 60 hours\n\n"
    "**Total: 100 hours**"
)
FAKE_RESPONSE_ID = "resp_integration_001"

# Minimum valid transcription (>= 50 chars as required by EstimationRequest)
VALID_TRANSCRIPTION = "Build an e-commerce platform with user auth and product catalog."


def _make_responses_mock(
    output_text: str = FAKE_OUTPUT,
    status: str = "completed",
    input_tokens: int = 600,
    output_tokens: int = 250,
    response_id: str = FAKE_RESPONSE_ID,
) -> MagicMock:
    """Build a minimal mock that mimics an OpenAI Responses API response object."""
    usage = MagicMock()
    usage.input_tokens = input_tokens
    usage.output_tokens = output_tokens
    usage.output_tokens_details = None

    response = MagicMock()
    response.status = status
    response.output_text = output_text
    response.usage = usage
    response.id = response_id
    return response


def _patch_responses_api(mock_response: MagicMock):
    """Context manager: patches _get_client so responses.create returns mock_response."""
    return patch(
        "app.services.openai_llm_service._get_client",
        return_value=MagicMock(
            responses=MagicMock(create=AsyncMock(return_value=mock_response))
        ),
    )


# --------------------------------------------------------------------------- #
# GET /api/v1/examples
# --------------------------------------------------------------------------- #
class TestGetExamples:
    def test_returns_200(self, client: TestClient):
        response = client.get("/api/v1/examples")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient):
        response = client.get("/api/v1/examples")
        assert isinstance(response.json(), list)

    def test_returns_all_examples(self, client: TestClient):
        response = client.get("/api/v1/examples")
        assert len(response.json()) == len(ESTIMATION_EXAMPLES)

    def test_each_item_has_required_fields(self, client: TestClient):
        response = client.get("/api/v1/examples")
        for item in response.json():
            assert "meeting_summary" in item
            assert "estimation_markdown" in item

    def test_meeting_summary_matches_source(self, client: TestClient):
        response = client.get("/api/v1/examples")
        items = response.json()
        for i, example in enumerate(ESTIMATION_EXAMPLES):
            assert items[i]["meeting_summary"] == example.meeting_summary


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — success path
# --------------------------------------------------------------------------- #
class TestCreateEstimation:
    def test_returns_200_with_valid_payload(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 200

    def test_response_contains_estimation_field(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert "estimation" in response.json()

    def test_estimation_value_matches_llm_output(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.json()["estimation"] == FAKE_OUTPUT

    def test_response_contains_cost_fields(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert "turn_cost_usd" in data
        assert "total_cost_usd" in data
        assert "estimated_precall_cost_usd" in data

    def test_response_contains_token_fields(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert "input_tokens" in data
        assert "output_tokens" in data
        assert "estimated_input_tokens" in data

    def test_response_contains_model_and_response_id(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert "model" in data
        assert data["response_id"] == FAKE_RESPONSE_ID

    def test_input_tokens_match_mock_usage(self, client: TestClient):
        mock_response = _make_responses_mock(input_tokens=600, output_tokens=250)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        data = response.json()
        assert data["input_tokens"] == 600
        assert data["output_tokens"] == 250

    def test_returns_422_when_transcription_is_missing(self, client: TestClient):
        response = client.post("/api/v1/estimate", json={})
        assert response.status_code == 422

    def test_returns_422_when_transcription_is_too_short(self, client: TestClient):
        """Transcriptions shorter than 50 characters are rejected — documents the current contract."""
        response = client.post("/api/v1/estimate", json={"transcription": "Too short."})
        assert response.status_code == 422


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — error propagation
# --------------------------------------------------------------------------- #
class TestCreateEstimationErrors:
    def test_returns_413_on_context_overflow(self, client: TestClient):
        from app.services.openai_llm_service import OpenAILLMService

        with patch.object(OpenAILLMService, "_count_tokens", return_value=999_999_999):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 413

    def test_error_detail_mentions_overflow(self, client: TestClient):
        from app.services.openai_llm_service import OpenAILLMService

        with patch.object(OpenAILLMService, "_count_tokens", return_value=999_999_999):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert "context" in response.json()["detail"].lower()

    def test_returns_500_when_api_status_is_failed(self, client: TestClient):
        mock_response = _make_responses_mock(status="failed")
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert response.status_code == 500


# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — pre-call two-step flow
# --------------------------------------------------------------------------- #

FAKE_REQUIREMENTS = (
    "1. User authentication with JWT\n"
    "2. Product catalog with search and filtering\n"
    "3. Shopping cart and checkout flow\n"
)


def _patch_responses_api_two_calls(
    pre_call_response: MagicMock,
    estimation_response: MagicMock,
):
    """Context manager: patches _get_client so two sequential responses.create
    calls return pre_call_response first, then estimation_response."""
    create_mock = AsyncMock(side_effect=[pre_call_response, estimation_response])
    return patch(
        "app.services.openai_llm_service._get_client",
        return_value=MagicMock(responses=MagicMock(create=create_mock)),
    ), create_mock


class TestCreateEstimationPreCall:
    def _pre_call_mock(self) -> MagicMock:
        return _make_responses_mock(
            output_text=FAKE_REQUIREMENTS,
            response_id="resp_pre_call",
            input_tokens=300,
            output_tokens=80,
        )

    def _estimation_mock(self) -> MagicMock:
        return _make_responses_mock(
            output_text=FAKE_OUTPUT,
            response_id="resp_estimation",
            input_tokens=400,
            output_tokens=200,
        )

    def test_returns_200_with_pre_call_enabled(self, client: TestClient):
        ctx, _ = _patch_responses_api_two_calls(self._pre_call_mock(), self._estimation_mock())
        with ctx:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.status_code == 200

    def test_response_contains_requirements_when_pre_call_enabled(self, client: TestClient):
        ctx, _ = _patch_responses_api_two_calls(self._pre_call_mock(), self._estimation_mock())
        with ctx:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.json()["requirements"] == FAKE_REQUIREMENTS

    def test_requirements_is_none_when_pre_call_disabled(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": False},
            )
        assert response.json()["requirements"] is None

    def test_pre_call_cost_usd_is_positive_when_pre_call_enabled(self, client: TestClient):
        ctx, _ = _patch_responses_api_two_calls(self._pre_call_mock(), self._estimation_mock())
        with ctx:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        data = response.json()
        assert data["pre_call_cost_usd"] is not None
        assert data["pre_call_cost_usd"] > 0

    def test_pre_call_cost_usd_is_none_when_pre_call_disabled(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": False},
            )
        assert response.json()["pre_call_cost_usd"] is None

    def test_estimation_field_contains_main_call_output(self, client: TestClient):
        ctx, _ = _patch_responses_api_two_calls(self._pre_call_mock(), self._estimation_mock())
        with ctx:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert response.json()["estimation"] == FAKE_OUTPUT

    def test_total_cost_is_greater_than_turn_cost_when_pre_call_enabled(self, client: TestClient):
        ctx, _ = _patch_responses_api_two_calls(self._pre_call_mock(), self._estimation_mock())
        with ctx:
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        data = response.json()
        assert data["total_cost_usd"] > data["turn_cost_usd"]

    def test_provider_called_twice_when_pre_call_enabled(self, client: TestClient):
        ctx, create_mock = _patch_responses_api_two_calls(
            self._pre_call_mock(), self._estimation_mock()
        )
        with ctx:
            client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "pre_call": True},
            )
        assert create_mock.call_count == 2

# --------------------------------------------------------------------------- #
# POST /api/v1/estimate — validation field
# --------------------------------------------------------------------------- #

WELL_FORMED_OUTPUT = """\
## E-commerce Platform Estimation

| Task | Hours | Cost |
|------|-------|------|
| Frontend | 40 | 4,000 EUR |
| Backend | 60 | 6,000 EUR |

Total hours: 100
Total cost: 10,000 EUR

### Recommended Team
- 2 Senior Developers

Estimated Duration: 6 weeks
"""


class TestEstimationValidation:
    def test_validation_field_present_by_default(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        assert "validation" in response.json()

    def test_validation_is_object_when_evaluate_true(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "evaluate": True},
            )
        data = response.json()
        assert data["validation"] is not None
        assert isinstance(data["validation"], dict)

    def test_validation_is_null_when_evaluate_false(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "evaluate": False},
            )
        assert response.json()["validation"] is None

    def test_validation_contains_score_field(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        validation = response.json()["validation"]
        assert "score" in validation
        assert isinstance(validation["score"], float)

    def test_validation_contains_issues_list(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        validation = response.json()["validation"]
        assert "issues" in validation
        assert isinstance(validation["issues"], list)

    def test_validation_contains_all_check_fields(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        validation = response.json()["validation"]
        for field in [
            "has_title",
            "has_breakdown_table",
            "has_totals_section",
            "has_team_section",
            "has_duration_section",
            "finish_reason_ok",
        ]:
            assert field in validation, f"Missing field: {field}"

    def test_well_formed_output_gives_perfect_score(self, client: TestClient):
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        validation = response.json()["validation"]
        assert validation["score"] == 1.0
        assert validation["issues"] == []

    def test_malformed_output_gives_issues(self, client: TestClient):
        mock_response = _make_responses_mock(output_text="Just some random text without structure.")
        with _patch_responses_api(mock_response):
            response = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        validation = response.json()["validation"]
        assert validation["score"] < 1.0
        assert len(validation["issues"]) > 0

    def test_evaluate_defaults_to_true(self, client: TestClient):
        """Omitting evaluate should behave the same as evaluate=True."""
        mock_response = _make_responses_mock(output_text=WELL_FORMED_OUTPUT)
        with _patch_responses_api(mock_response):
            without_flag = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION},
            )
        with _patch_responses_api(mock_response):
            with_flag = client.post(
                "/api/v1/estimate",
                json={"transcription": VALID_TRANSCRIPTION, "evaluate": True},
            )
        assert without_flag.json()["validation"] is not None
        assert with_flag.json()["validation"] is not None
