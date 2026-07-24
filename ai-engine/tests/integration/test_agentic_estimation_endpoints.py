from __future__ import annotations

from fastapi.testclient import TestClient

from app.agents.schemas import AgenticEstimationResponse, AgenticEstimate, AgenticRunState
from app.agents.service import AgenticRunNotFoundError, AgenticRunNotPausedError
from app.api.estimations import get_agentic_estimation_service
from app.main import app


def _sample_estimate(*, status: str = "validated") -> AgenticEstimate:
    return AgenticEstimate(
        components=[],
        total_amount=40.0,
        unit="hours",
        method="arithmetic_mean",
        assumptions=[],
        status=status,
        confidence=0.9,
        validation={"errors": []},
    )


def _sample_response(*, response_id: str = "estimate-123", status: str = "validated") -> AgenticEstimationResponse:
    return AgenticEstimationResponse(
        estimation="# Agentic estimate",
        structured_result=_sample_estimate(status=status),
        trace=[],
        model="gpt-5",
        response_id=response_id,
        input_tokens=0,
        output_tokens=0,
        reasoning_tokens=0,
        prompt_version="v1",
        reasoning_effort="medium",
    )


def _valid_request_payload() -> dict[str, str]:
    return {
        "transcription": "Necesitamos una API backend, app mobile, y pruebas de integracion con ERP.",
    }


def test_agentic_state_returns_200_with_run_state(client: TestClient):
    class StubService:
        async def get_state(self, *, estimation_id: str) -> AgenticRunState:
            return AgenticRunState(
                estimation_id=estimation_id,
                state="completed",
                status="validated",
                structured_estimate=_sample_estimate(),
                confidence=0.9,
                validation={"errors": []},
                routing_history=[{"step": 0, "next_agent": "finish"}],
                agent_contributions=[],
            )

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.get("/api/v1/estimate/agentic/estimate-123/state")
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "completed"
    assert body["status"] == "validated"
    assert body["estimation_id"] == "estimate-123"


def test_agentic_state_returns_404_when_run_is_missing(client: TestClient):
    class StubService:
        async def get_state(self, *, estimation_id: str) -> AgenticRunState:
            return AgenticRunState(
                estimation_id=estimation_id,
                state="missing",
                status="missing",
            )

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.get("/api/v1/estimate/agentic/unknown-id/state")
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 404
    assert "Unknown estimation_id" in response.json()["detail"]


def test_agentic_resume_maps_not_found_to_404(client: TestClient):
    class StubService:
        async def resume(
            self,
            *,
            estimation_id: str,
            decision: dict[str, object],
            prompt_version: str = "v1",
        ) -> AgenticEstimationResponse:
            raise AgenticRunNotFoundError(f"Unknown estimation_id: {estimation_id}")

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.post(
            "/api/v1/estimate/agentic/missing-id/resume",
            json={"decision": {"action": "approve"}},
        )
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 404
    assert "Unknown estimation_id" in response.json()["detail"]


def test_agentic_resume_maps_not_paused_to_409(client: TestClient):
    class StubService:
        async def resume(
            self,
            *,
            estimation_id: str,
            decision: dict[str, object],
            prompt_version: str = "v1",
        ) -> AgenticEstimationResponse:
            raise AgenticRunNotPausedError(f"No pending human review for estimation_id={estimation_id}")

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.post(
            "/api/v1/estimate/agentic/finished-id/resume",
            json={"decision": {"action": "approve"}},
        )
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 409
    assert "No pending human review" in response.json()["detail"]


def test_agentic_start_still_returns_response_contract(client: TestClient):
    class StubService:
        async def estimate(self, request, *, prompt_version: str = "v1") -> AgenticEstimationResponse:
            return _sample_response(response_id="estimate-start-1", status="validated")

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.post("/api/v1/estimate/agentic", json=_valid_request_payload())
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["response_id"] == "estimate-start-1"
    assert body["structured_result"]["status"] == "validated"


def test_supervisor_start_accepts_estimation_id(client: TestClient):
    class StubService:
        async def estimate(self, request, *, prompt_version: str = "v1", estimation_id: str | None = None) -> AgenticEstimationResponse:
            return _sample_response(response_id=estimation_id or "generated-id", status="validated")

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.post(
            "/api/v1/estimate/supervisor",
            json={
                "transcript": _valid_request_payload()["transcription"],
                "estimation_id": "run-s14-001",
            },
        )
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 200
    body = response.json()
    assert body["response_id"] == "run-s14-001"


def test_supervisor_resume_uses_typed_decision_and_maps_409(client: TestClient):
    class StubService:
        async def resume(
            self,
            *,
            estimation_id: str,
            decision: dict[str, object],
            prompt_version: str = "v1",
        ) -> AgenticEstimationResponse:
            raise AgenticRunNotPausedError(f"No pending human review for estimation_id={estimation_id}")

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.post(
            "/api/v1/estimate/supervisor/run-s14-001/resume",
            json={"decision": "approve", "note": "validated by PM"},
        )
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 409


def test_supervisor_state_returns_404_for_unknown_run(client: TestClient):
    class StubService:
        async def get_state(self, *, estimation_id: str) -> AgenticRunState:
            return AgenticRunState(estimation_id=estimation_id, state="missing", status="missing")

    app.dependency_overrides[get_agentic_estimation_service] = lambda: StubService()
    try:
        response = client.get("/api/v1/estimate/supervisor/unknown/state")
    finally:
        app.dependency_overrides.pop(get_agentic_estimation_service, None)

    assert response.status_code == 404
