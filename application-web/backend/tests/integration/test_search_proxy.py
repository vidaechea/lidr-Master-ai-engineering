from __future__ import annotations

from unittest.mock import AsyncMock, patch


SEARCH_PAYLOAD = {
    "query": "oauth backend",
    "k": 2,
    "search_time_ms": 9,
    "results": [
        {
            "chunk_id": 156,
            "document_id": 12,
            "chunk_type": "budget_component",
            "content": "Backend service implementation with JWT-based authentication...",
            "distance": 0.231,
            "metadata": {"scope": "backend"},
        }
    ],
}


class TestSemanticSearchProxy:
    async def test_public_search_requires_auth(self, client):
        response = await client.post("/v1/estimations/search", json={"query": "oauth backend", "k": 2})
        assert response.status_code == 401

    async def test_public_search_returns_proxy_payload(self, client, auth_headers):
        with patch(
            "app.services.ai_client.search_semantic",
            AsyncMock(return_value=SEARCH_PAYLOAD),
        ) as mock_search:
            response = await client.post(
                "/v1/estimations/search",
                json={"query": "oauth backend", "k": 2},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json() == SEARCH_PAYLOAD
        mock_search.assert_awaited_once_with({"query": "oauth backend", "k": 2})

    async def test_legacy_search_keeps_compatibility_route(self, client, auth_headers):
        with patch(
            "app.services.ai_client.search_semantic",
            AsyncMock(return_value=SEARCH_PAYLOAD),
        ) as mock_search:
            response = await client.post(
                "/v1/estimations/embeddings/search",
                json={"query": "oauth backend", "k": 2},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json() == SEARCH_PAYLOAD
        mock_search.assert_awaited_once_with(
            {"query": "oauth backend", "k": 2},
            use_public_contract=False,
        )