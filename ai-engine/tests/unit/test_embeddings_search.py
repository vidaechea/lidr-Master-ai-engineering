from __future__ import annotations

import importlib
from dataclasses import dataclass

import pytest
from fastapi import HTTPException

from app.api.embeddings import search
from app.domain.schemas.embeddings import SearchRequest

router_module = importlib.import_module("app.api.embeddings")


@dataclass
class _FakeRow:
    id: int
    document_id: int
    chunk_type: str
    content: str
    distance: float
    metadata: dict


class _FakeResult:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows

    def all(self) -> list[_FakeRow]:
        return self._rows


class _FakeAsyncSession:
    def __init__(self, rows: list[_FakeRow]) -> None:
        self._rows = rows
        self.executed_stmt = None

    async def execute(self, stmt):
        self.executed_stmt = stmt
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_search_returns_top_k_results(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        captured["texts"] = texts
        captured["model"] = model
        return [[0.01, 0.02, 0.03]]

    monkeypatch.setattr(router_module, "embed_texts", fake_embed_texts)

    rows = [
        _FakeRow(
            id=156,
            document_id=12,
            chunk_type="budget_component",
            content="Backend service implementation with JWT-based authentication...",
            distance=0.231,
            metadata={"scope": "backend", "technologies": ["python", "fastapi"]},
        ),
        _FakeRow(
            id=157,
            document_id=13,
            chunk_type="budget_component",
            content="Frontend portal with OAuth login flow...",
            distance=0.287,
            metadata={"scope": "frontend", "technologies": ["angular"]},
        ),
    ]
    session = _FakeAsyncSession(rows=rows)

    payload = SearchRequest(query="REST API with OAuth authentication for fintech sector", k=5)
    response = await search(payload, session=session)

    assert captured["texts"] == [payload.query]
    assert captured["model"] == "text-embedding-3-small"
    assert response.query == payload.query
    assert response.k == 5
    assert response.search_time_ms >= 0
    assert len(response.results) == 2
    assert response.results[0].chunk_id == 156
    assert response.results[0].document_id == 12
    assert response.results[0].distance == 0.231


@pytest.mark.asyncio
async def test_search_returns_empty_results_when_no_chunks_found(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        return [[0.4, 0.5, 0.6]]

    monkeypatch.setattr(router_module, "embed_texts", fake_embed_texts)

    session = _FakeAsyncSession(rows=[])
    payload = SearchRequest(query="query with no hits", k=3)

    response = await search(payload, session=session)

    assert response.query == payload.query
    assert response.k == 3
    assert response.results == []


@pytest.mark.asyncio
async def test_search_returns_http_400_when_embedding_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        raise ValueError("OPENAI_API_KEY is required for embedding generation")

    monkeypatch.setattr(router_module, "embed_texts", failing_embed_texts)

    session = _FakeAsyncSession(rows=[])
    payload = SearchRequest(query="REST API", k=5)

    with pytest.raises(HTTPException) as exc_info:
        await search(payload, session=session)

    assert exc_info.value.status_code == 400
    assert "OPENAI_API_KEY is required" in str(exc_info.value.detail)
