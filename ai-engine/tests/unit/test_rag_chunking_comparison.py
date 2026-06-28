from __future__ import annotations

import importlib

import pytest

from app.api.embeddings import compare_chunking
from app.generation.rag.schemas import Budget, CompareRequest

comparison_module = importlib.import_module("app.generation.rag.analysis.comparison")


def _sample_budget() -> Budget:
    return Budget.model_validate(
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
    )


class _FakeRuntimeConfig:
    async def effective(self, key: str) -> str:
        if key == "PROPOSITIONAL_CHUNKER_MODEL":
            return "gpt-5.4-mini"
        if key == "CONTEXTUAL_CHUNKER_MODEL":
            return "gpt-5.4-mini"
        return "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_compare_chunking_returns_stats_and_query_results(monkeypatch):
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

    response = await compare_chunking(
        CompareRequest(
            budgets=[_sample_budget()],
            queries=["OAuth authentication backend"],
            strategies=["structural", "fixed_size"],
            top_k=2,
        ),
        runtime_config=_FakeRuntimeConfig(),
    )

    assert set(response.stats_per_strategy) == {"structural", "fixed_size"}
    assert response.stats_per_strategy["structural"].total_chunks >= 1
    assert response.queries_per_strategy["structural"][0].query == "OAuth authentication backend"
    assert response.queries_per_strategy["structural"][0].results[0].similarity >= 0.0
