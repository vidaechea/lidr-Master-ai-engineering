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
        "app.services.llm_service._get_client",
        return_value=MagicMock(
            responses=MagicMock(create=AsyncMock(return_value=mock_response))
        ),
    )


# --------------------------------------------------------------------------- #
# GET /estimations/examples
# --------------------------------------------------------------------------- #
class TestGetExamples:
    def test_returns_200(self, client: TestClient):
        response = client.get("/estimations/examples")
        assert response.status_code == 200

    def test_returns_list(self, client: TestClient):
        response = client.get("/estimations/examples")
        assert isinstance(response.json(), list)

    def test_returns_all_examples(self, client: TestClient):
        response = client.get("/estimations/examples")
        assert len(response.json()) == len(ESTIMATION_EXAMPLES)

    def test_each_item_has_required_fields(self, client: TestClient):
        response = client.get("/estimations/examples")
        for item in response.json():
            assert "meeting_summary" in item
            assert "estimation" in item

    def test_meeting_summary_matches_source(self, client: TestClient):
        response = client.get("/estimations/examples")
        items = response.json()
        for i, example in enumerate(ESTIMATION_EXAMPLES):
            assert items[i]["meeting_summary"] == example.meeting_summary


# --------------------------------------------------------------------------- #
# POST /estimations/ — success path
# --------------------------------------------------------------------------- #
class TestCreateEstimation:
    def test_returns_200_with_valid_payload(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert response.status_code == 200

    def test_response_contains_estimation_field(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert "estimation" in response.json()

    def test_estimation_value_matches_llm_output(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert response.json()["estimation"] == FAKE_OUTPUT

    def test_response_contains_cost_fields(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        data = response.json()
        assert "turn_cost_usd" in data
        assert "total_cost_usd" in data
        assert "estimated_precall_cost_usd" in data

    def test_response_contains_token_fields(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        data = response.json()
        assert "input_tokens" in data
        assert "output_tokens" in data
        assert "estimated_input_tokens" in data

    def test_response_contains_model_and_response_id(self, client: TestClient):
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        data = response.json()
        assert "model" in data
        assert data["response_id"] == FAKE_RESPONSE_ID

    def test_input_tokens_match_mock_usage(self, client: TestClient):
        mock_response = _make_responses_mock(input_tokens=600, output_tokens=250)
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        data = response.json()
        assert data["input_tokens"] == 600
        assert data["output_tokens"] == 250

    def test_returns_422_when_description_is_missing(self, client: TestClient):
        response = client.post("/estimations/", json={})
        assert response.status_code == 422

    def test_returns_200_when_description_is_empty_string(self, client: TestClient):
        """An empty string passes schema validation — documents the current contract."""
        mock_response = _make_responses_mock()
        with _patch_responses_api(mock_response):
            response = client.post("/estimations/", json={"description": ""})
        assert response.status_code == 200


# --------------------------------------------------------------------------- #
# POST /estimations/ — error propagation
# --------------------------------------------------------------------------- #
class TestCreateEstimationErrors:
    def test_returns_413_on_context_overflow(self, client: TestClient):
        import app.services.llm_service as svc

        with patch.object(svc._openai_service, "_count_tokens", return_value=999_999_999):
            response = client.post(
                "/estimations/",
                json={"description": "Build something very long"},
            )
        assert response.status_code == 413

    def test_error_detail_mentions_overflow(self, client: TestClient):
        import app.services.llm_service as svc

        with patch.object(svc._openai_service, "_count_tokens", return_value=999_999_999):
            response = client.post(
                "/estimations/",
                json={"description": "Build something very long"},
            )
        assert "context" in response.json()["detail"].lower()

    def test_returns_500_when_api_status_is_failed(self, client: TestClient):
        mock_response = _make_responses_mock(status="failed")
        with _patch_responses_api(mock_response):
            response = client.post(
                "/estimations/",
                json={"description": "Build something"},
            )
        assert response.status_code == 500
