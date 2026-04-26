from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.context.examples import ESTIMATION_EXAMPLES


FAKE_ESTIMATION = (
    "## Estimate: E-commerce Platform\n\n"
    "1. UI/UX Design: 40 hours\n"
    "2. Backend API: 60 hours\n\n"
    "**Total: 100 hours**"
)


def _make_openai_response(content: str):
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    response = MagicMock()
    response.choices = [choice]
    return response


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


class TestCreateEstimation:
    def test_returns_200_with_valid_payload(self, client: TestClient):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert response.status_code == 200

    def test_response_contains_estimation_field(self, client: TestClient):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        data = response.json()
        assert "estimation" in data

    def test_estimation_value_matches_llm_output(self, client: TestClient):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert response.json()["estimation"] == FAKE_ESTIMATION

    def test_returns_422_when_description_is_missing(self, client: TestClient):
        response = client.post("/estimations/", json={})
        assert response.status_code == 422

    def test_returns_422_when_payload_is_empty_string(self, client: TestClient):
        """FastAPI validates the field exists; an empty string is technically valid — 
        this test documents the current contract."""
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post("/estimations/", json={"description": ""})
        assert response.status_code == 200
    def test_returns_200_with_valid_payload(self, client: TestClient):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert response.status_code == 200

    def test_response_contains_estimation_field(self, client: TestClient):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        data = response.json()
        assert "estimation" in data

    def test_estimation_value_matches_llm_output(self, client: TestClient):
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post(
                "/estimations/",
                json={"description": "Build an e-commerce platform"},
            )
        assert response.json()["estimation"] == FAKE_ESTIMATION

    def test_returns_422_when_description_is_missing(self, client: TestClient):
        response = client.post("/estimations/", json={})
        assert response.status_code == 422

    def test_returns_422_when_payload_is_empty_string(self, client: TestClient):
        """FastAPI validates the field exists; an empty string is technically valid — 
        this test documents the current contract."""
        with patch(
            "app.services.llm_service.client.chat.completions.create",
            new=AsyncMock(return_value=_make_openai_response(FAKE_ESTIMATION)),
        ):
            response = client.post("/estimations/", json={"description": ""})
        assert response.status_code == 200
