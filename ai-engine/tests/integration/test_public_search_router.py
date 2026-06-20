from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.generation.rag.schemas import SearchResponse
from app.persistence.database import get_async_session


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


async def _fake_session_override():
    yield object()


def test_public_search_matches_legacy_route(client) -> None:
    from app.main import app

    app.dependency_overrides[get_async_session] = _fake_session_override
    try:
        with patch(
            "app.api.embeddings._execute_semantic_search",
            AsyncMock(return_value=SearchResponse(**SEARCH_PAYLOAD)),
        ) as mock_search:
            public_response = client.post("/api/v1/search", json={"query": "oauth backend", "k": 2})
            legacy_response = client.post(
                "/api/v1/embeddings/search",
                json={"query": "oauth backend", "k": 2},
            )

        assert public_response.status_code == 200
        assert legacy_response.status_code == 200
        assert public_response.json() == legacy_response.json()
        assert public_response.json() == SEARCH_PAYLOAD
        assert mock_search.await_count == 2
    finally:
        app.dependency_overrides.pop(get_async_session, None)