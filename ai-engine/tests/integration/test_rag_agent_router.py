from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.dependencies import get_semantic_retriever
from app.generation.rag.schemas import RetrievalResult, RetrievedChunk
from app.main import app


def test_agent_structure_route_returns_trace(client):
    response = client.post(
        "/api/v1/rag/agent/structure",
        json={
            "query": {
                "search_text": "build a fintech backend",
                "sector": "fintech",
                "year_from": 2023,
                "year_to": 2024,
                "chunk_types": ["budget_component"],
                "keywords": ["backend", "oauth"],
            },
            "model": "gpt-5",
            "reasoning_effort": "medium",
            "persona": "be conservative",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert "estimate" in body
    assert "agent_trace" in body
    assert body["agent_trace"]["steps"][0]["tool"] == "propose_structure"


def test_agent_hours_route_runs_hybrid_recovery(client):
    empty_retrieval = RetrievalResult(
        query="Auth OAuth backend",
        top_k=5,
        candidates_evaluated=0,
        low_confidence=True,
        chunks=[],
    )
    recovered_retrieval = RetrievalResult(
        query="Auth OAuth backend",
        top_k=5,
        candidates_evaluated=1,
        low_confidence=False,
        chunks=[
            RetrievedChunk(
                source_id="src-1",
                chunk_id=1,
                document_id=1,
                chunk_type="budget_component",
                content="Component: OAuth backend\nEstimated hours: 64",
                distance=0.1,
                metadata={"budget_id": "BUD-1", "estimated_hours": 64},
            )
        ],
    )

    retriever = SimpleNamespace()
    # First call is deterministic pass, second call is recovery pass.
    retriever.search_with_query = AsyncMock(side_effect=[empty_retrieval, recovered_retrieval])

    app.dependency_overrides[get_semantic_retriever] = lambda: retriever
    try:
        response = client.post(
            "/api/v1/rag/agent/hours",
            json={
                "modules": [
                    {
                        "name": "Auth",
                        "tasks": [{"name": "OAuth backend"}],
                    }
                ],
                "model": "gpt-5-mini",
                "reasoning_effort": "low",
                "max_iterations": 2,
                "search_top_k": 5,
                "search_distance_threshold": 0.35,
            },
        )
    finally:
        app.dependency_overrides.pop(get_semantic_retriever, None)

    assert response.status_code == 200
    body = response.json()
    assert body["tasks"][0]["has_match"] is True
    assert body["tasks"][0]["estimated_hours"] is not None
    assert body["agent_trace"]["steps"][0]["tool"] == "search_budgets"
