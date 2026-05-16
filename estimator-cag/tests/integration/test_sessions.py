"""Integration tests for POST /api/v1/sessions.

Uses FastAPI's synchronous TestClient (no real LLM calls).
The SessionStore singleton is reset before each test to guarantee isolation.
"""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

UUID_V4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


@pytest.fixture(autouse=True)
def reset_session_store():
    """Clear the in-memory store before every test to prevent state leakage."""
    from app.services import sessions as sessions_module
    sessions_module.store._sessions.clear()
    yield
    sessions_module.store._sessions.clear()


# ---------------------------------------------------------------------------
# POST /api/v1/sessions
# ---------------------------------------------------------------------------


class TestCreateSession:
    def test_returns_201(self, client: TestClient):
        response = client.post("/api/v1/sessions")
        assert response.status_code == 201

    def test_response_body_has_session_id_key(self, client: TestClient):
        response = client.post("/api/v1/sessions")
        assert "session_id" in response.json()

    def test_session_id_is_uuid_v4(self, client: TestClient):
        response = client.post("/api/v1/sessions")
        session_id = response.json()["session_id"]
        assert UUID_V4_RE.match(session_id), f"Not a valid UUID v4: {session_id}"

    def test_each_call_returns_different_session_id(self, client: TestClient):
        id_a = client.post("/api/v1/sessions").json()["session_id"]
        id_b = client.post("/api/v1/sessions").json()["session_id"]
        assert id_a != id_b

    def test_session_is_persisted_in_store(self, client: TestClient):
        from app.services.sessions import store
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        assert store.get(session_id) is not None

    def test_session_history_starts_empty(self, client: TestClient):
        from app.services.sessions import store
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        assert len(store.get(session_id).history) == 0

    def test_session_metadata_starts_with_defaults(self, client: TestClient):
        from app.services.sessions import store
        session_id = client.post("/api/v1/sessions").json()["session_id"]
        meta = store.get(session_id).metadata
        assert meta.project_name is None
        assert meta.assumed_team_size is None
        assert meta.mentioned_technologies == []

    def test_content_type_is_json(self, client: TestClient):
        response = client.post("/api/v1/sessions")
        assert "application/json" in response.headers["content-type"]

    def test_no_request_body_required(self, client: TestClient):
        """Endpoint must work with an empty POST — no body schema expected."""
        response = client.post("/api/v1/sessions", json=None)
        assert response.status_code == 201

    def test_multiple_sessions_stored_independently(self, client: TestClient):
        from app.services.sessions import store
        ids = [client.post("/api/v1/sessions").json()["session_id"] for _ in range(5)]
        assert len(set(ids)) == 5
        assert len(store) == 5


# ---------------------------------------------------------------------------
# Helpers shared by estimate tests
# ---------------------------------------------------------------------------

VALID_TRANSCRIPT = (
    "Build a React and FastAPI e-commerce platform with PostgreSQL. "
    "The team will have 3 developers. Project name is ShopCore."
)

FAKE_ESTIMATION = (
    "## Estimate: ShopCore\n\n"
    "| Phase | Hours |\n|---|---|\n| Backend | 80 |\n\n**Total: 80 hours**"
)


def _make_litellm_mock(text: str = FAKE_ESTIMATION) -> MagicMock:
    usage = MagicMock()
    usage.prompt_tokens = 400
    usage.completion_tokens = 200

    message = MagicMock()
    message.content = text

    choice = MagicMock()
    choice.message = message
    choice.finish_reason = "stop"

    response = MagicMock()
    response.choices = [choice]
    response.usage = usage
    response.id = "resp_test_session"
    return response


def _patch_litellm(mock_response: MagicMock | None = None):
    return patch(
        "app.services.litellm_service.LiteLLMRouterService.complete",
        AsyncMock(return_value=mock_response or _make_litellm_mock()),
    )


# ---------------------------------------------------------------------------
# POST /api/v1/sessions/{session_id}/estimate
# ---------------------------------------------------------------------------


class TestSessionEstimate:
    def _create_session(self, client: TestClient) -> str:
        return client.post("/api/v1/sessions").json()["session_id"]

    def test_returns_200_with_valid_transcript(self, client: TestClient):
        sid = self._create_session(client)
        with _patch_litellm():
            resp = client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        assert resp.status_code == 200

    def test_response_contains_estimation_field(self, client: TestClient):
        sid = self._create_session(client)
        with _patch_litellm():
            resp = client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        assert "estimation" in resp.json()

    def test_unknown_session_returns_404(self, client: TestClient):
        with _patch_litellm():
            resp = client.post(
                "/api/v1/sessions/nonexistent-id/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        assert resp.status_code == 404

    def test_short_transcript_returns_422(self, client: TestClient):
        sid = self._create_session(client)
        resp = client.post(
            f"/api/v1/sessions/{sid}/estimate",
            data={"transcript": "Too short"},
        )
        assert resp.status_code == 422

    def test_metadata_populated_after_estimation(self, client: TestClient):
        from app.services.sessions import store

        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        meta = store.get(sid).metadata
        assert "react" in meta.mentioned_technologies
        assert "fastapi" in meta.mentioned_technologies
        assert "postgresql" in meta.mentioned_technologies

    def test_metadata_team_size_extracted(self, client: TestClient):
        from app.services.sessions import store

        sid = self._create_session(client)
        with _patch_litellm(
            _make_litellm_mock("Estimated for a team of 3 developers.")
        ):
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        meta = store.get(sid).metadata
        assert meta.assumed_team_size == 3

    def test_metadata_project_name_extracted(self, client: TestClient):
        from app.services.sessions import store

        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        meta = store.get(sid).metadata
        assert meta.project_name == "ShopCore"

    def test_metadata_accumulates_across_turns(self, client: TestClient):
        from app.services.sessions import store

        sid = self._create_session(client)

        with _patch_litellm(_make_litellm_mock("Backend will use FastAPI.")):
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": "Build a React frontend application with 30 chars here."},
            )

        with _patch_litellm(_make_litellm_mock("Database: PostgreSQL recommended.")):
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": "Add a PostgreSQL database layer to the existing system."},
            )

        meta = store.get(sid).metadata
        assert "react" in meta.mentioned_technologies
        assert "postgresql" in meta.mentioned_technologies

    def test_metadata_scope_set_from_transcript(self, client: TestClient):
        from app.services.sessions import store

        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        meta = store.get(sid).metadata
        assert meta.agreed_scope is not None
        assert len(meta.agreed_scope) > 0

