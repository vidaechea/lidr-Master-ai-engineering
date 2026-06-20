from __future__ import annotations

import importlib

comparison_module = importlib.import_module("app.generation.rag.analysis.comparison")


def _sample_payload() -> dict:
    return {
        "budgets": [
            {
                "budget_id": "BUD-2024-014",
                "client_metadata": {"name": "FintechCorp", "sector": "finance", "country": "ES"},
                "project_summary": "Mobile banking API with OAuth 2.0 authentication",
                "main_technology": "ruby_on_rails",
                "year": 2024,
                "total_estimated_hours": 480,
                "components": [
                    {
                        "component_id": "AUTH-001",
                        "name": "OAuth backend",
                        "description": "Implementation of OAuth flows with JWT",
                        "tech_stack": ["ruby_on_rails", "postgresql", "redis"],
                        "estimated_hours": 120,
                        "complexity": "high",
                        "dependencies": [],
                    }
                ],
            }
        ],
        "queries": ["OAuth authentication backend"],
        "strategies": ["structural", "fixed_size"],
        "top_k": 2,
    }


def test_compare_chunking_endpoint_returns_200(client, monkeypatch):
    def fake_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            if "oauth" in lowered or "jwt" in lowered:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors

    monkeypatch.setattr(comparison_module, "embed_texts", fake_embed_texts)

    response = client.post("/api/v1/embeddings/compare", json=_sample_payload())

    assert response.status_code == 200
    body = response.json()
    assert set(body["stats_per_strategy"]) == {"structural", "fixed_size"}
    assert body["queries_per_strategy"]["structural"][0]["query"] == "OAuth authentication backend"


def test_compare_chunking_endpoint_rejects_unknown_strategy(client):
    payload = _sample_payload()
    payload["strategies"] = ["missing"]

    response = client.post("/api/v1/embeddings/compare", json=payload)

    assert response.status_code == 400
    assert "Unknown strategy" in response.json()["detail"]