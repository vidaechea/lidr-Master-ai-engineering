from __future__ import annotations

import json
from dataclasses import dataclass

import pytest
from fastapi import HTTPException
from fastapi.responses import JSONResponse

from app.api.embeddings import ingest
from app.generation.rag.ingest_service import DuplicateDocumentError
from app.domain.schemas.embeddings import IngestPersistRequest
from app.generation.rag.schemas import IngestPersistResponse


@dataclass
class _FakeIngestService:
    response: IngestPersistResponse | None = None
    error: Exception | None = None
    calls: int = 0

    async def ingest(self, *, source_path: str, document_type: str, budget) -> IngestPersistResponse:
        self.calls += 1
        if self.error is not None:
            raise self.error
        assert self.response is not None
        return self.response


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
    service = _FakeIngestService(error=DuplicateDocumentError(42))
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content=_valid_budget_content(),
    )

    response = await ingest(payload, service=service)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 409
    assert json.loads(response.body.decode("utf-8")) == {
        "detail": "Document already ingested",
        "document_id": 42,
    }
    assert service.calls == 1


@pytest.mark.asyncio
async def test_ingest_persists_document_and_chunks_in_single_transaction(
) -> None:
    service = _FakeIngestService(
        response=IngestPersistResponse(
            document_id=42,
            chunks_created=2,
            embedding_dimension=3,
            ingestion_time_ms=1,
        )
    )
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content=_valid_budget_content(),
    )

    response = await ingest(payload, service=service)

    assert response.document_id == 42
    assert response.chunks_created == 2
    assert response.embedding_dimension == 3
    assert response.ingestion_time_ms >= 0

    assert service.calls == 1


@pytest.mark.asyncio
async def test_ingest_returns_500_and_rolls_back_when_embedder_fails(
) -> None:
    service = _FakeIngestService(error=RuntimeError("OpenAI temporary failure"))
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content=_valid_budget_content(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await ingest(payload, service=service)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal processing error"
    assert service.calls == 1


@pytest.mark.asyncio
async def test_ingest_returns_400_when_content_is_invalid() -> None:
    service = _FakeIngestService(
        response=IngestPersistResponse(
            document_id=1,
            chunks_created=1,
            embedding_dimension=3,
            ingestion_time_ms=1,
        )
    )
    payload = IngestPersistRequest(
        source_path="data/budgets/budget_2024_q1_fintech.json",
        document_type="historical_budget",
        content={"invalid": "shape"},
    )

    with pytest.raises(HTTPException) as exc_info:
        await ingest(payload, service=service)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Invalid budget content"
    assert service.calls == 0
