"""Semantic retriever over the pgvector store (Session 8).

Embeds the query with the SAME model used at ingest time (mixing embedding
models makes distances meaningless) and ranks chunks by cosine distance via
SQL. No vector index and no metadata filtering yet — both are built live in
the session on top of this baseline.
"""

from __future__ import annotations

import asyncio
import time

import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.generation.rag.embedding.embedder import OpenAIEmbedder
from app.generation.rag.schemas import EstimationQuery, SearchResponse, SearchResultItem, RetrievalResult, RetrievedChunk
from app.generation.rag.store.repository import ChunkStore

log = structlog.get_logger()


class SemanticRetriever:
    """k-NN retrieval: embed the query, rank chunks by cosine distance."""

    def __init__(
        self,
        embedder: OpenAIEmbedder,
        session_factory: async_sessionmaker,
        store: ChunkStore,
    ) -> None:
        self._embedder = embedder
        self._session_factory = session_factory
        self._store = store

    async def search(self, *, query: str, k: int) -> SearchResponse:
        """Search for k nearest chunks by cosine distance (legacy, backward-compatible)."""
        started = time.perf_counter()

        # Sync OpenAI client → thread, same reasoning as in the ingest path.
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query)

        async with self._session_factory() as session:
            rows, _candidates_evaluated = await self._store.search(session, query_vector=query_vector, k=k)

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
            results=len(response.results),
            search_time_ms=elapsed_ms,
        )
        return response

    async def search_with_query(
        self,
        *,
        query: EstimationQuery,
        k: int,
        distance_threshold: float | None = None,
    ) -> RetrievalResult:
        """Search for chunks matching EstimationQuery with metadata filters.

        Returns RetrievalResult with candidates_evaluated and low_confidence flag.
        """
        started = time.perf_counter()

        # Embed the compact search text from the query
        query_vector = await asyncio.to_thread(self._embedder.embed_one, query.search_text)

        async with self._session_factory() as session:
            rows, candidates_evaluated = await self._store.search_with_filters(
                session,
                query_vector=query_vector,
                k=k,
                sector=query.sector,
                year_from=query.year_from,
                year_to=query.year_to,
                chunk_types=query.chunk_types if query.chunk_types else None,
            )

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
            results=len(chunks),
            candidates_evaluated=candidates_evaluated,
            low_confidence=low_confidence,
            search_time_ms=elapsed_ms,
        )
        return result
