"""Integration tests for POST /api/v1/sessions.

Uses FastAPI's synchronous TestClient (no real LLM calls).
The SessionStore singleton is reset before each test to guarantee isolation.
"""
from __future__ import annotations

import re
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from app.schemas.llm import LLMObservableResponse, LLMUsage
from app.schemas.observation import TurnObservedEvent

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


def _make_litellm_mock(text: str = FAKE_ESTIMATION) -> LLMObservableResponse:
    """Build a mock LLMObservableResponse object."""
    return LLMObservableResponse(
        model="gpt-4o-mini",
        content=text,
        usage=LLMUsage(
            prompt_tokens=400,
            completion_tokens=200,
            total_tokens=600,
        ),
        latency_ms=500.0,
        cost_usd=Decimal("0.001"),
        response_id="resp_test_session",
    )


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
        assert meta.project_name is not None
        assert meta.project_name.endswith("ShopCore")

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


class TestGetSessionState:
    def _create_session(self, client: TestClient) -> str:
        return client.post("/api/v1/sessions").json()["session_id"]

    def test_returns_200_with_existing_session(self, client: TestClient):
        sid = self._create_session(client)
        resp = client.get(f"/api/v1/sessions/{sid}")
        assert resp.status_code == 200

    def test_returns_metadata_and_history_shape(self, client: TestClient):
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        assert body["session_id"] == sid
        assert "project_metadata" in body
        assert "history" in body
        assert "turn_count" in body
        assert isinstance(body["project_metadata"]["mentioned_technologies"], list)

    def test_unknown_session_returns_404(self, client: TestClient):
        resp = client.get("/api/v1/sessions/nonexistent-id")
        assert resp.status_code == 404

    # -----------------------------------------------------------------------
    # New tests for explicitly exposed fields
    # -----------------------------------------------------------------------

    def test_response_includes_message_count(self, client: TestClient):
        """Verify message_count is exposed and counts all messages."""
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        assert "message_count" in body
        assert isinstance(body["message_count"], int)
        # After one estimate call, we should have at least user and assistant messages
        assert body["message_count"] >= 2

    def test_message_count_greater_or_equal_to_turn_count(self, client: TestClient):
        """message_count should always be >= turn_count * 2 (user + assistant per turn)."""
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        # At minimum: turn_count user messages, turn_count assistant responses
        assert body["message_count"] >= body["turn_count"] * 2

    def test_response_includes_anchors_count(self, client: TestClient):
        """Verify anchors_count is exposed."""
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        assert "anchors_count" in body
        assert isinstance(body["anchors_count"], int)
        assert body["anchors_count"] >= 0

    def test_response_includes_summary_chars(self, client: TestClient):
        """Verify summary_chars is exposed."""
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        assert "summary_chars" in body
        assert isinstance(body["summary_chars"], int)
        assert body["summary_chars"] >= 0

    def test_response_includes_last_resolved_tier(self, client: TestClient):
        """Verify last_resolved_tier is exposed (can be null initially)."""
        sid = self._create_session(client)
        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        assert "last_resolved_tier" in body
        # Initially null, but field must be present
        assert body["last_resolved_tier"] is None

    def test_response_includes_last_tier_rule(self, client: TestClient):
        """Verify last_tier_rule is exposed (can be null initially)."""
        sid = self._create_session(client)
        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        assert "last_tier_rule" in body
        # Initially null, but field must be present
        assert body["last_tier_rule"] is None

    def test_all_required_fields_present_in_response(self, client: TestClient):
        """Verify all new fields are present in the response body."""
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        resp = client.get(f"/api/v1/sessions/{sid}")
        body = resp.json()
        required_fields = [
            "session_id",
            "project_metadata",
            "history",
            "turn_count",
            "message_count",
            "anchors_count",
            "summary_chars",
            "last_resolved_tier",
            "last_tier_rule",
            "anchors",
        ]
        for field in required_fields:
            assert field in body, f"Missing required field: {field}"


# ---------------------------------------------------------------------------
# POST /api/v1/sessions/{session_id}/estimate → turn_observed event
# ---------------------------------------------------------------------------

# Turn context fields: the 13 core observation fields in TurnObservedEvent that
# capture session state, transcript size, memory metrics, and token/cost data.
# Excludes LLM-identity fields (model, response_id) which travel in the same event.
_TURN_CONTEXT_FIELDS = {
    "turn_index",
    "session_id",
    "enriched_transcript_chars",
    "attachments_total_chars",
    "messages_in_window",
    "anchors_count",
    "summary_chars",
    "tokens_in",
    "tokens_out",
    "cost_usd",
    "latency_ms",
    "cache_hit_kind",
    "last_resolved_tier",
}
# Full set of fields – the schema also carries model + response_id.
_ALL_TURN_OBSERVED_FIELDS = set(TurnObservedEvent.model_fields.keys())


class TestSessionEstimateTurnObservedEvent:
    """Verify that POST /sessions/{id}/estimate emits a turn_observed log event
    containing the 13 turn-context fields on every call."""

    def _create_session(self, client: TestClient) -> str:
        return client.post("/api/v1/sessions").json()["session_id"]

    def _single_turn_observed_event(self, logs: list[dict]) -> dict:
        turn_logs = [entry for entry in logs if entry.get("event") == "turn_observed"]
        assert len(turn_logs) == 1, (
            "Expected exactly one turn_observed log entry per request, "
            f"found {len(turn_logs)}"
        )
        return turn_logs[0]

    def test_turn_observed_event_is_emitted(self, client: TestClient):
        """Exactly one turn_observed entry must be emitted per request."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            resp = client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        assert resp.status_code == 200
        self._single_turn_observed_event(logs)

    def test_turn_observed_one_event_per_request_across_two_calls(self, client: TestClient):
        """Each estimate call must emit one and only one turn_observed event."""
        sid = self._create_session(client)

        with _patch_litellm(), capture_logs() as first_logs:
            first_resp = client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        assert first_resp.status_code == 200
        self._single_turn_observed_event(first_logs)

        with _patch_litellm(), capture_logs() as second_logs:
            second_resp = client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        assert second_resp.status_code == 200
        self._single_turn_observed_event(second_logs)

    def test_turn_observed_contains_all_block1_fields(self, client: TestClient):
        """The emitted event must contain every one of the 13 turn-context fields."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        missing = _TURN_CONTEXT_FIELDS - set(event.keys())
        assert not missing, f"turn_observed is missing turn-context fields: {missing}"

    def test_turn_observed_contains_all_schema_fields(self, client: TestClient):
        """The emitted event must contain all 15 fields defined in TurnObservedEvent."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        missing = _ALL_TURN_OBSERVED_FIELDS - set(event.keys())
        assert not missing, f"turn_observed is missing fields: {missing}"

    def test_turn_observed_session_id_matches_request(self, client: TestClient):
        """session_id in the event must match the session used for the call."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        assert event["session_id"] == sid

    def test_turn_observed_turn_index_is_1_for_first_turn(self, client: TestClient):
        """turn_index must be 1 for the very first estimation in a new session."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        assert event["turn_index"] == 1

    def test_turn_observed_turn_index_increments_on_second_call(self, client: TestClient):
        """turn_index must increase by 1 on each successive estimation call."""
        sid = self._create_session(client)
        with _patch_litellm():
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        assert event["turn_index"] == 2

    def test_turn_observed_tokens_are_positive(self, client: TestClient):
        """tokens_in and tokens_out must be positive integers."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        assert event["tokens_in"] > 0
        assert event["tokens_out"] > 0

    def test_turn_observed_enriched_transcript_chars_matches_transcript(
        self, client: TestClient
    ):
        """enriched_transcript_chars must equal the length of the submitted transcript
        when no attachments are provided."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        assert event["enriched_transcript_chars"] == len(VALID_TRANSCRIPT)

    def test_turn_observed_attachments_total_chars_is_zero_without_files(
        self, client: TestClient
    ):
        """attachments_total_chars must be 0 when no files are uploaded."""
        sid = self._create_session(client)
        with _patch_litellm(), capture_logs() as logs:
            client.post(
                f"/api/v1/sessions/{sid}/estimate",
                data={"transcript": VALID_TRANSCRIPT},
            )

        event = self._single_turn_observed_event(logs)
        assert event["attachments_total_chars"] == 0

