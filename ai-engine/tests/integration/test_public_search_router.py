from __future__ import annotations

import asyncio
from app.dependencies import get_semantic_retriever
from app.main import app

SEARCH_PAYLOAD = {
    "query": "oauth backend",
    "k": 2,
    "search_time_ms": 7,
    "results": [
        {
            "chunk_id": 156,
            "document_id": 12,
            "chunk_type": "budget_component",
            "content": "Backend service implementation with JWT-based authentication...",
            "distance": 0.231,
            "metadata": {"scope": "backend", "technologies": ["python", "fastapi"]},
        }
    ],
}


class _StubRetriever:
    async def search(self, *, query: str, k: int):
        await asyncio.sleep(0)
        payload = dict(SEARCH_PAYLOAD)
        payload["query"] = query
        payload["k"] = k
        from app.generation.rag.schemas import SearchResponse

        return SearchResponse(**payload)


def test_public_search_matches_legacy_route(client) -> None:
    app.dependency_overrides[get_semantic_retriever] = lambda: _StubRetriever()
    try:
        public_response = client.post("/api/v1/search", json={"query": "oauth backend", "k": 2})
        legacy_response = client.post(
            "/api/v1/embeddings/search",
            json={"query": "oauth backend", "k": 2},
        )

        assert public_response.status_code == 200
        assert legacy_response.status_code == 200
        assert public_response.json() == legacy_response.json()
        assert public_response.json() == SEARCH_PAYLOAD
    finally:
        app.dependency_overrides.pop(get_semantic_retriever, None)