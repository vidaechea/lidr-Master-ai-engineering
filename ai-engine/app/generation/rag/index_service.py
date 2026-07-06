from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog

from app.generation.rag.ingest_service import DuplicateDocumentError, RagIngestService
from app.generation.rag.schemas import Budget

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class CorpusExpansionResult:
    documents_indexed: int
    documents_skipped: int
    chunks_created: int


class CorpusIndexService:
    """Batch-add documents to the RAG corpus using the existing ingest service."""

    def __init__(self, ingest: RagIngestService) -> None:
        self._ingest = ingest

    async def expand(
        self,
        documents: list[Budget],
        *,
        document_type: str = "historical_budget",
        chunk_type: str = "budget_component",
        source_prefix: str = "corpus-expansion",
        on_progress: Callable[[int], None] | None = None,
    ) -> CorpusExpansionResult:
        indexed = 0
        skipped = 0
        chunks_created = 0

        for document in documents:
            source_path = f"{source_prefix}::{document.budget_id}"
            try:
                response = await self._ingest.ingest(
                    source_path=source_path,
                    document_type=document_type,
                    budget=document,
                )
                indexed += 1
                chunks_created += response.chunks_created
            except DuplicateDocumentError:
                skipped += 1
                log.info("corpus_expansion_skip_duplicate", source_path=source_path, chunk_type=chunk_type)

            if on_progress is not None:
                on_progress(indexed + skipped)

        log.info(
            "corpus_expansion_done",
            documents_indexed=indexed,
            documents_skipped=skipped,
            chunks_created=chunks_created,
            chunk_type=chunk_type,
        )
        return CorpusExpansionResult(
            documents_indexed=indexed,
            documents_skipped=skipped,
            chunks_created=chunks_created,
        )