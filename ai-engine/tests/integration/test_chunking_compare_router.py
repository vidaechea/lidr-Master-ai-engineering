from __future__ import annotations

import importlib
import asyncio

from app.dependencies import get_runtime_config
from app.main import app

comparison_module = importlib.import_module("app.generation.rag.analysis.comparison")


class _StubRuntimeConfig:
    async def effective(self, key: str) -> str:
        await asyncio.sleep(0)
        if key == "PROPOSITIONAL_CHUNKER_MODEL":
            return "gpt-5.4-mini"
        if key == "CONTEXTUAL_CHUNKER_MODEL":
            return "claude-haiku-4-5-20251001"
        if key == "LLM_MODEL":
            return "gpt-4o-mini"
        if key == "LLM_FALLBACK":
            return "claude-haiku-4-5-20251001"
        return "gpt-4o-mini"


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


def test_compare_chunking_uses_runtime_chunker_models(client, monkeypatch):
    def fake_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    app.dependency_overrides[get_runtime_config] = lambda: _StubRuntimeConfig()
    monkeypatch.setattr(comparison_module, "embed_texts", fake_embed_texts)

    payload = _sample_payload()
    payload["strategies"] = ["propositional", "contextual_retrieval"]
    payload["queries"] = ["backend auth"]
    payload["top_k"] = 1

    try:
        response = client.post("/api/v1/embeddings/compare", json=payload)
    finally:
        app.dependency_overrides.pop(get_runtime_config, None)

    assert response.status_code == 200
    body = response.json()

    prop_metadata = body["queries_per_strategy"]["propositional"][0]["results"][0]["metadata"]
    ctx_metadata = body["queries_per_strategy"]["contextual_retrieval"][0]["results"][0]["metadata"]

    assert prop_metadata["chunker_model"] == "gpt-5.4-mini"
    assert ctx_metadata["chunker_model"] == "claude-haiku-4-5-20251001"