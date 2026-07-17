from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_graph_stream_proxy_returns_202(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client.rag_graph_start_stream",
        AsyncMock(
            return_value={
                "estimation_id": "run-1",
                "state": "running",
                "pending_gate": None,
                "activity": [],
            }
        ),
    )

    response = await client.post(
        "/v1/rag/graph/stream",
        headers=auth_headers,
        json={"transcript": "x" * 40},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["estimation_id"] == "run-1"
    assert body["state"] == "running"


@pytest.mark.asyncio
async def test_graph_resume_stream_proxy(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client.rag_graph_resume_stream",
        AsyncMock(
            return_value={
                "estimation_id": "run-1",
                "state": "running",
                "pending_gate": None,
                "activity": [{"seq": 1, "node": "hours", "label": "Hours", "message": "ok", "ts": "2026-01-01"}],
            }
        ),
    )

    response = await client.post(
        "/v1/rag/graph/run-1/resume-stream",
        headers=auth_headers,
        json={"decision": {"approved": True}},
    )

    assert response.status_code == 202
    assert response.json()["activity"][0]["node"] == "hours"


@pytest.mark.asyncio
async def test_graph_state_and_progress_proxy(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client.rag_graph_state",
        AsyncMock(
            return_value={
                "estimation_id": "run-2",
                "state": "paused",
                "pending_gate": {
                    "gate": "structure_review",
                    "estimation_id": "run-2",
                    "payload": {"modules": []},
                },
            }
        ),
    )
    monkeypatch.setattr(
        "app.services.ai_client.rag_graph_progress",
        AsyncMock(
            return_value={
                "estimation_id": "run-2",
                "state": "paused",
                "pending_gate": {
                    "gate": "structure_review",
                    "estimation_id": "run-2",
                    "payload": {"modules": []},
                },
                "activity": [{"seq": 1, "node": "structure", "label": "Structure", "message": "ok", "ts": "2026-01-01"}],
            }
        ),
    )

    state_response = await client.get("/v1/rag/graph/run-2/state", headers=auth_headers)
    progress_response = await client.get("/v1/rag/graph/run-2/progress", headers=auth_headers)

    assert state_response.status_code == 200
    assert state_response.json()["pending_gate"]["gate"] == "structure_review"

    assert progress_response.status_code == 200
    assert progress_response.json()["activity"][0]["node"] == "structure"


@pytest.mark.asyncio
async def test_graph_proposal_proxy(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client.rag_graph_proposal",
        AsyncMock(
            return_value={
                "estimation_id": "run-3",
                "title": "Propuesta comercial",
                "body_markdown": "## Propuesta",
            }
        ),
    )

    response = await client.post("/v1/rag/graph/run-3/proposal", headers=auth_headers)

    assert response.status_code == 200
    assert response.json()["title"] == "Propuesta comercial"
