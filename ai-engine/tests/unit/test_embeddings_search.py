from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.embeddings import search
from app.domain.schemas.embeddings import SearchRequest, SearchResponse


class _FakeRetriever:
    def __init__(self, response: SearchResponse | None = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls = 0
        self.last_kwargs: dict[str, object] = {}

    async def search(self, *, query: str, k: int, mode: str, rerank: bool) -> SearchResponse:
        self.calls += 1
        self.last_kwargs = {
            "query": query,
            "k": k,
            "mode": mode,
            "rerank": rerank,
        }
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


@pytest.mark.asyncio
async def test_search_returns_top_k_results() -> None:
    retriever = _FakeRetriever(
        response=SearchResponse(
            query="REST API with OAuth authentication for fintech sector",
            k=5,
            search_time_ms=1,
            results=[],
        )
    )

    payload = SearchRequest(query="REST API with OAuth authentication for fintech sector", k=5)
    response = await search(payload, retriever=retriever)

    assert retriever.calls == 1
    assert retriever.last_kwargs == {
        "query": payload.query,
        "k": 5,
        "mode": "vector",
        "rerank": False,
    }
    assert response.query == payload.query
    assert response.k == 5
    assert response.search_time_ms >= 0
    assert response.results == []


@pytest.mark.asyncio
async def test_search_returns_empty_results_when_no_chunks_found() -> None:
    retriever = _FakeRetriever(
        response=SearchResponse(query="query with no hits", k=3, search_time_ms=1, results=[])
    )
    payload = SearchRequest(query="query with no hits", k=3)

    response = await search(payload, retriever=retriever)

    assert response.query == payload.query
    assert response.k == 3
    assert response.results == []


@pytest.mark.asyncio
async def test_search_returns_http_500_when_retriever_fails() -> None:
    retriever = _FakeRetriever(error=ValueError("OPENAI_API_KEY is required for embedding generation"))
    payload = SearchRequest(query="REST API", k=5)

    with pytest.raises(HTTPException) as exc_info:
        await search(payload, retriever=retriever)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal processing error"
