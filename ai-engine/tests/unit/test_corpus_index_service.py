from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.generation.rag.index_service import CorpusIndexService
from app.generation.rag.ingest_service import DuplicateDocumentError
from app.generation.rag.schemas import Budget, BudgetComponent, ClientMetadata, IngestPersistResponse


def _budget(budget_id: str) -> Budget:
    return Budget(
        budget_id=budget_id,
        client_metadata=ClientMetadata(name="Acme", sector="saas", country="ES"),
        project_summary="Portal project",
        main_technology="python",
        year=2024,
        total_estimated_hours=40,
        components=[
            BudgetComponent(
                component_id="DISC-1",
                name="Discovery",
                description="Discovery work",
                tech_stack=["python"],
                estimated_hours=40,
                complexity="medium",
                dependencies=[],
            )
        ],
    )


@pytest.mark.asyncio
async def test_expand_skips_duplicates_and_reports_progress() -> None:
    ingest = AsyncMock()
    ingest.ingest = AsyncMock(
        side_effect=[
            IngestPersistResponse(document_id=1, chunks_created=2, embedding_dimension=1536, ingestion_time_ms=10),
            DuplicateDocumentError(1),
        ]
    )
    service = CorpusIndexService(ingest=ingest)
    progress: list[int] = []

    result = await service.expand([_budget("B1"), _budget("B2")], on_progress=progress.append)

    assert result.documents_indexed == 1
    assert result.documents_skipped == 1
    assert result.chunks_created == 2
    assert progress == [1, 2]