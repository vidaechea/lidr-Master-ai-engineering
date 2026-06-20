from __future__ import annotations

from unittest.mock import AsyncMock, patch


COMPARE_PAYLOAD = {
    "stats_per_strategy": {
        "structural": {
            "total_chunks": 3,
            "total_tokens": 180,
            "avg_tokens_per_chunk": 60.0,
            "min_tokens": 40,
            "max_tokens": 80,
            "estimated_cost_usd": 0.000004,
        },
        "fixed_size": {
            "total_chunks": 5,
            "total_tokens": 260,
            "avg_tokens_per_chunk": 52.0,
            "min_tokens": 20,
            "max_tokens": 70,
            "estimated_cost_usd": 0.000005,
        },
    },
    "queries_per_strategy": {
        "structural": [
            {
                "query": "oauth backend",
                "results": [
                    {
                        "chunk_id": "BUD-1::AUTH-001",
                        "payload": "OAuth component",
                        "similarity": 0.91,
                        "metadata": {"budget_id": "BUD-1"},
                    }
                ],
            }
        ],
        "fixed_size": [],
    },
}


class TestChunkingComparisonEndpoint:
    async def test_compare_chunking_requires_auth(self, client):
        response = await client.post("/v1/estimations/rag/chunking-comparison", json={"queries": []})
        assert response.status_code == 401

    async def test_compare_chunking_returns_proxy_payload(self, client, auth_headers):
        with patch("app.services.rag_lab_service.load_sample_budgets", return_value=[{"budget_id": "BUD-1"}]):
            with patch(
                "app.services.ai_client.compare_chunking",
                AsyncMock(return_value=COMPARE_PAYLOAD),
            ) as mock_compare:
                response = await client.post(
                    "/v1/estimations/rag/chunking-comparison",
                    json={"queries": ["oauth backend"], "strategies": ["structural"], "top_k": 3},
                    headers=auth_headers,
                )

        assert response.status_code == 200
        assert response.json()["stats_per_strategy"]["structural"]["total_chunks"] == 3
        mock_compare.assert_awaited_once_with(
            {
                "budgets": [{"budget_id": "BUD-1"}],
                "queries": ["oauth backend"],
                "strategies": ["structural"],
                "top_k": 3,
            }
        )