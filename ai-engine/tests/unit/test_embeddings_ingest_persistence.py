from __future__ import annotations

import importlib
import json
from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.api.embeddings import ingest
from app.domain.schemas.embeddings import IngestPersistRequest

router_module = importlib.import_module("app.api.embeddings")


@dataclass
class _FakeResult:
    value: int | None

    def scalar_one_or_none(self) -> int | None:
        return self.value


class _TxContext:
    def __init__(self, session: "_FakeAsyncSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_TxContext":
        self._session.tx_entered += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._session.tx_committed += 1
        else:
            self._session.tx_rolled_back += 1


class _FakeAsyncSession:
    def __init__(self, existing_document_id: int | None = None) -> None:
        self._existing_document_id = existing_document_id
        self.added: list[object] = []
        self.added_all: list[object] = []
        self.tx_entered = 0
        self.tx_committed = 0
        self.tx_rolled_back = 0

    async def execute(self, _stmt) -> _FakeResult:
        return _FakeResult(self._existing_document_id)

    def begin(self) -> _TxContext:
        return _TxContext(self)

    def add(self, row: object) -> None:
        self.added.append(row)

    def add_all(self, rows: list[object]) -> None:
        self.added_all.extend(rows)

    async def flush(self) -> None:
        if self.added:
            document = self.added[-1]
            if getattr(document, "id", None) is None:
                setattr(document, "id", 42)


def _valid_budget_content() -> dict:
    return {
        "budget_id": "BUD-2024-001",
        "client_metadata": {"name": "Acme Corp", "sector": "fintech", "country": "ES"},
        "project_summary": "API and portal revamp",
        "main_technology": "python",
        "year": 2024,
        "total_estimated_hours": 180,
        "components": [
            {
                "component_id": "API-001",
                "name": "API core",
                "description": "Build core API",
                "tech_stack": ["python", "fastapi"],
                "estimated_hours": 80,
                "complexity": "medium",
                "dependencies": [],
            },
            {
                "component_id": "WEB-001",
                "name": "Web portal",
                "description": "Build frontend",
                "tech_stack": ["angular"],
                "estimated_hours": 100,
                "complexity": "high",
                "dependencies": ["API-001"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_ingest_returns_409_when_document_already_exists() -> None:
    session = _FakeAsyncSession(existing_document_id=42)
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content=_valid_budget_content(),
    )

    response = await ingest(payload, session=session)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert json.loads(response.body.decode("utf-8")) == {
        "detail": "Document already ingested",
        "document_id": 42,
    }
    assert session.tx_entered == 0


@pytest.mark.asyncio
async def test_ingest_persists_document_and_chunks_in_single_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChunker:
        def chunk(self, _budgets):
            return [
                type("Chunk", (), {"text": "chunk one", "metadata": {"component_id": "A"}})(),
                type("Chunk", (), {"text": "chunk two", "metadata": {"component_id": "B"}})(),
            ]

    def fake_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        assert texts == ["chunk one", "chunk two"]
        assert model == "text-embedding-3-small"
        return [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    monkeypatch.setattr(router_module, "JSONStructuralChunker", FakeChunker)
    monkeypatch.setattr(router_module, "embed_texts", fake_embed_texts)

    session = _FakeAsyncSession(existing_document_id=None)
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content=_valid_budget_content(),
    )

    response = await ingest(payload, session=session)

    assert response.document_id == 42
    assert response.chunks_created == 2
    assert response.embedding_dimension == 3
    assert response.ingestion_time_ms >= 0

    assert session.tx_entered == 1
    assert session.tx_committed == 1
    assert session.tx_rolled_back == 0
    assert len(session.added) == 1
    assert len(session.added_all) == 2
    assert all(getattr(chunk, "document_id") == 42 for chunk in session.added_all)


@pytest.mark.asyncio
async def test_ingest_returns_500_and_rolls_back_when_embedder_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeChunker:
        def chunk(self, _budgets):
            return [type("Chunk", (), {"text": "chunk one", "metadata": {}})()]

    def failing_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        raise RuntimeError("OpenAI temporary failure")

    monkeypatch.setattr(router_module, "JSONStructuralChunker", FakeChunker)
    monkeypatch.setattr(router_module, "embed_texts", failing_embed_texts)

    session = _FakeAsyncSession(existing_document_id=None)
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content=_valid_budget_content(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await ingest(payload, session=session)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal processing error"
    assert session.tx_entered == 1
    assert session.tx_committed == 0
    assert session.tx_rolled_back == 1


@pytest.mark.asyncio
async def test_ingest_returns_400_when_content_is_invalid() -> None:
    session = _FakeAsyncSession(existing_document_id=None)
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content={"invalid": "shape"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await ingest(payload, session=session)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid budget content"
