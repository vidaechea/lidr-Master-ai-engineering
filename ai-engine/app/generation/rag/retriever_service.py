"""Semantic retriever over the pgvector store (Session 8).

Embeds the query with the SAME model used at ingest time (mixing embedding
models makes distances meaningless) and ranks chunks by cosine distance via
SQL. No vector index and no metadata filtering yet — both are built live in
the session on top of this baseline.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.generation.rag.embedding.embedder import OpenAIEmbedder
from app.generation.rag.reranker import CrossEncoderReranker, RerankCandidate
from app.generation.rag.schemas import (
    EstimationQuery,
    RetrievalResult,
    RetrievedChunk,
    SearchResponse,
    SearchResultItem,
)
from app.generation.rag.store.repository import ChunkStore

log = structlog.get_logger()


class SemanticRetriever:
    """k-NN retrieval: embed the query, rank chunks by cosine distance."""

    def __init__(
        self,
        embedder: OpenAIEmbedder,
        session_factory: async_sessionmaker,
        store: ChunkStore,
        reranker: CrossEncoderReranker | None = None,
    ) -> None:
        self._embedder = embedder
        self._session_factory = session_factory
        self._store = store
        self._reranker = reranker

    async def search(
        self,
        *,
        query: str,
        k: int,
        mode: Literal["vector", "hybrid"] = "vector",
        rerank: bool = False,
    ) -> SearchResponse:
        """Search using vector-only or hybrid retrieval, with optional reranking."""
        started = time.perf_counter()

        # Sync OpenAI client → thread, same reasoning as in the ingest path.
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query)

        per_branch_k = max(k, settings.rag_pipeline_rerank_recall_top_k)
        rows: list
        candidates_evaluated: int

        if rerank and self._reranker is None:
            raise RuntimeError("Reranking requested but CrossEncoder reranker is not available")

        async with self._session_factory() as session:
            if mode == "hybrid":
                rows, candidates_evaluated = await self._store.search_hybrid(
                    session,
                    query_text=query,
                    query_vector=query_vector,
                    k=per_branch_k,
                    rrf_k=settings.rag_pipeline_rrf_k,
                    per_branch_k=per_branch_k,
                )
            else:
                rows, candidates_evaluated = await self._store.search(
                    session,
                    query_vector=query_vector,
                    k=per_branch_k,
                )

        if rerank and self._reranker is not None and rows:
            top_k = min(k, settings.rag_pipeline_rerank_final_top_k)
            rows = self._rerank_rows(query=query, rows=rows, top_k=top_k)
        else:
            rows = rows[:k]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        response = SearchResponse(
            query=query,
            k=k,
            search_time_ms=elapsed_ms,
            results=[
                SearchResultItem(
                    chunk_id=row.id,
                    document_id=row.document_id,
                    chunk_type=row.chunk_type,
                    content=row.content,
                    distance=float(row.distance),
                    metadata=row.metadata_,
                )
                for row in rows
            ],
        )
        log.info(
            "rag_search_done",
            query=query[:80],
            k=k,
            mode=mode,
            rerank=rerank,
            results=len(response.results),
            candidates_evaluated=candidates_evaluated,
            search_time_ms=elapsed_ms,
        )
        return response

    async def _retrieve_rows_with_filters(
        self,
        *,
        query_text: str,
        query_vector: list[float],
        mode: Literal["vector", "hybrid"],
        top_k: int,
        sector: str | None,
        year_from: int | None,
        year_to: int | None,
        chunk_types: list[str] | None,
    ) -> tuple[list, int]:
        async with self._session_factory() as session:
            if mode == "hybrid":
                return await self._store.search_hybrid_with_filters(
                    session,
                    query_text=query_text,
                    query_vector=query_vector,
                    k=top_k,
                    rrf_k=settings.rag_pipeline_rrf_k,
                    per_branch_k=top_k,
                    sector=sector,
                    year_from=year_from,
                    year_to=year_to,
                    chunk_types=chunk_types,
                )

            return await self._store.search_with_filters(
                session,
                query_vector=query_vector,
                k=top_k,
                sector=sector,
                year_from=year_from,
                year_to=year_to,
                chunk_types=chunk_types,
            )

    async def search_with_query(
        self,
        *,
        query: EstimationQuery,
        k: int,
        distance_threshold: float | None = None,
        mode: Literal["vector", "hybrid"] | None = None,
        rerank: bool | None = None,
    ) -> RetrievalResult:
        """Search for chunks matching EstimationQuery with metadata filters.

        Returns RetrievalResult with candidates_evaluated and low_confidence flag.
        """
        started = time.perf_counter()
        resolved_mode: Literal["vector", "hybrid"] = mode or settings.rag_pipeline_search_mode
        resolved_rerank = settings.rag_pipeline_rerank_enabled if rerank is None else rerank
        recall_top_k = max(k, settings.rag_pipeline_rerank_recall_top_k) if resolved_rerank else k

        if resolved_rerank and self._reranker is None:
            raise RuntimeError("Reranking requested but CrossEncoder reranker is not available")

        # Embed the compact search text from the query
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query.search_text)

        rows, candidates_evaluated = await self._retrieve_rows_with_filters(
            query_text=query.search_text,
            query_vector=query_vector,
            mode=resolved_mode,
            top_k=recall_top_k,
            sector=query.sector,
            year_from=query.year_from,
            year_to=query.year_to,
            chunk_types=query.chunk_types if query.chunk_types else None,
        )

        if resolved_rerank and self._reranker is not None and rows:
            final_top_k = min(k, settings.rag_pipeline_rerank_final_top_k)
            rows = self._rerank_rows(query=query.search_text, rows=rows, top_k=final_top_k)
        else:
            rows = rows[:k]

        elapsed_ms = int((time.perf_counter() - started) * 1000)

        chunks = [
            RetrievedChunk(
                source_id=f"src-{row.id}",
                chunk_id=row.id,
                document_id=row.document_id,
                chunk_type=row.chunk_type,
                content=row.content,
                distance=float(row.distance),
                metadata=row.metadata_,
            )
            for row in rows
        ]

        # Determine low_confidence: no results or all results exceed distance threshold
        low_confidence = False
        if len(chunks) == 0:
            low_confidence = True
        elif distance_threshold is not None:
            low_confidence = all(chunk.distance > distance_threshold for chunk in chunks)

        result = RetrievalResult(
            query=query.search_text,
            top_k=k,
            candidates_evaluated=candidates_evaluated,
            low_confidence=low_confidence,
            chunks=chunks,
        )

        log.info(
            "rag_search_with_query_done",
            query_text=query.search_text[:80],
            k=k,
            mode=resolved_mode,
            rerank=resolved_rerank,
            results=len(chunks),
            candidates_evaluated=candidates_evaluated,
            low_confidence=low_confidence,
            search_time_ms=elapsed_ms,
        )
        return result

    def _rerank_rows(self, *, query: str, rows: list, top_k: int) -> list:
        if self._reranker is None or not rows:
            return rows[:top_k]

        scored = self._reranker.rerank(
            query=query,
            candidates=[RerankCandidate(item_id=row.id, text=row.content) for row in rows],
            top_k=top_k,
        )
        row_by_id = {row.id: row for row in rows}
        reranked_rows = [row_by_id[item.item_id] for item in scored if item.item_id in row_by_id]
        return reranked_rows
