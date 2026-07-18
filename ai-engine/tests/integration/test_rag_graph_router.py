from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.dependencies import get_graph_run_service
from app.domain.schemas.graph_estimation import GraphRunState
from app.main import app


@dataclass
class _FakeGraphService:
    should_raise_not_found: bool = False
    state_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "estimation_id": "run-123",
            "state": "paused",
            "pending_gate": {
                "gate": "structure_review",
                "estimation_id": "run-123",
                "payload": {"modules": []},
            },
            "complexity": "medium",
            "structure": {"modules": []},
            "task_hours": [],
            "estimate": None,
            "analysis_report": None,
            "proposal": None,
            "status": None,
            "errors": [],
        }
    )
    progress_payload: dict[str, Any] = field(
        default_factory=lambda: {
            "estimation_id": "run-123",
            "state": "running",
            "pending_gate": None,
            "complexity": None,
            "structure": None,
            "task_hours": [],
            "estimate": None,
            "analysis_report": None,
            "proposal": None,
            "status": None,
            "errors": [],
            "activity": [
                {
                    "seq": 1,
                    "node": "classifier",
                    "label": "Classifier",
                    "message": "Iniciando",
                    "ts": "2026-01-01T00:00:00+00:00",
                }
            ],
        }
    )
    proposal_payload: dict[str, str] = field(
        default_factory=lambda: {
            "estimation_id": "run-123",
            "title": "Propuesta comercial",
            "body_markdown": "## Propuesta",
        }
    )
    started: list[tuple[str, str]] = field(default_factory=list)
    resumed: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def start(self, *, estimation_id: str, transcript: str):
        self.started.append((estimation_id, transcript))
        return self.state_payload

    async def resume(self, *, estimation_id: str, decision: dict[str, Any]):
        self.resumed.append((estimation_id, decision))
        return self.state_payload

    def get_state(self, *, estimation_id: str):
        if self.should_raise_not_found:
            from app.generation.rag.graph_runtime import GraphRunError

            raise GraphRunError("Unknown estimation_id.")
        return GraphRunState(**self.state_payload)

    def get_progress(self, *, estimation_id: str):
        if self.should_raise_not_found:
            from app.generation.rag.graph_runtime import GraphRunError

            raise GraphRunError("Unknown estimation_id.")
        return self.progress_payload

    def build_proposal(self, *, estimation_id: str):
        return self.proposal_payload

    def record_error(self, *, estimation_id: str, message: str) -> None:
        _ = (estimation_id, message)


def test_graph_stream_start_returns_202_running(client):
    fake_service = _FakeGraphService()
    app.dependency_overrides[get_graph_run_service] = lambda: fake_service
    try:
        response = client.post(
            "/api/v1/rag/graph/stream",
            json={"transcript": "x" * 40, "estimation_id": "run-abc"},
        )
    finally:
        app.dependency_overrides.pop(get_graph_run_service, None)

    assert response.status_code == 202
    body = response.json()
    assert body["estimation_id"] == "run-abc"
    assert body["state"] == "running"


def test_graph_resume_returns_409_without_pending_gate(client):
    fake_service = _FakeGraphService()
    fake_service.state_payload = {
        **fake_service.state_payload,
        "state": "completed",
        "pending_gate": None,
    }
    app.dependency_overrides[get_graph_run_service] = lambda: fake_service
    try:
        response = client.post(
            "/api/v1/rag/graph/run-123/resume-stream",
            json={"decision": {"approved": True}},
        )
    finally:
        app.dependency_overrides.pop(get_graph_run_service, None)

    assert response.status_code == 409
    assert "No pending human gate" in response.json()["detail"]


def test_graph_state_returns_404_when_unknown(client):
    fake_service = _FakeGraphService(should_raise_not_found=True)
    app.dependency_overrides[get_graph_run_service] = lambda: fake_service
    try:
        response = client.get("/api/v1/rag/graph/missing/state")
    finally:
        app.dependency_overrides.pop(get_graph_run_service, None)

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown estimation_id."


def test_graph_progress_and_proposal_return_payload(client):
    fake_service = _FakeGraphService()
    app.dependency_overrides[get_graph_run_service] = lambda: fake_service
    try:
        progress = client.get("/api/v1/rag/graph/run-123/progress")
        proposal = client.post("/api/v1/rag/graph/run-123/proposal")
    finally:
        app.dependency_overrides.pop(get_graph_run_service, None)

    assert progress.status_code == 200
    assert progress.json()["activity"][0]["node"] == "classifier"

    assert proposal.status_code == 200
    assert proposal.json()["title"] == "Propuesta comercial"
