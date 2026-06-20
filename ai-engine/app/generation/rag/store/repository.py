"""Async data-access layer for the vector store.

The store never opens or commits sessions: the caller (ingest service,
retriever) owns the ``AsyncSession`` so a whole ingest — duplicate check,
document row, chunk rows — fits in ONE transaction. A failure anywhere rolls
everything back and leaves no orphan ``documents`` row.
"""

from __future__ import annotations

from sqlalchemy import Row, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.generation.rag.schemas import EmbeddedChunk
from app.generation.rag.store.models import ChunkRow, DocumentRow, EMBEDDING_DIMENSIONS

# The structural chunker emits one chunk per budget component; the vocabulary
# is queryable thanks to the index on ``chunk_type`` (live-session filters).
BUDGET_COMPONENT = "budget_component"


class ChunkStore:
    """CRUD + similarity search over ``documents``/``chunks``."""

    async def find_document_id(self, session: AsyncSession, source_path: str) -> int | None:
        """Return the id of the document already ingested from ``source_path``,
        or ``None``. Backs the application-level 409 duplicate guard."""
        stmt = select(DocumentRow.id).where(DocumentRow.source_path == source_path)
        return (await session.execute(stmt)).scalar_one_or_none()

    async def persist_document_with_chunks(
        self,
        session: AsyncSession,
        *,
        source_path: str,
        document_type: str,
        doc_metadata: dict,
        embedded_chunks: list[EmbeddedChunk],
    ) -> int:
        """Insert the document row plus all its chunk rows. No commit here —
        the caller's transaction decides when (and whether) anything lands."""
        document = DocumentRow(
            source_path=source_path,
            document_type=document_type,
            metadata_=doc_metadata,
        )
        session.add(document)
        await session.flush()  # assigns document.id without committing

        session.add_all(
            ChunkRow(
                document_id=document.id,
                chunk_type=BUDGET_COMPONENT,
                content=chunk.text,
                embedding=chunk.embedding,
                metadata_=chunk.metadata,
            )
            for chunk in embedded_chunks
        )
        return document.id

    async def search(
        self, session: AsyncSession, *, query_vector: list[float], k: int
    ) -> tuple[list[Row], int]:
        """k nearest chunks by cosine distance (``<=>``), sequential scan.

        Cosine over L2/inner product: OpenAI embeddings are normalized so the
        ranking would be equivalent, but cosine keeps us aligned with the RAG
        literature AND with the ``vector_cosine_ops`` operator class of the
        HNSW index the live session adds — operator/index mismatch makes
        Postgres silently ignore the index.

        Returns a tuple of (filtered_results, candidates_evaluated) where:
        - filtered_results: k nearest matching chunks
        - candidates_evaluated: total chunks evaluated before applying k limit
        """
        return await self.search_with_filters(
            session,
            query_vector=query_vector,
            k=k,
            sector=None,
            year_from=None,
            year_to=None,
            chunk_types=None,
        )

    async def search_with_filters(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        k: int,
        sector: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        chunk_types: list[str] | None = None,
    ) -> tuple[list[Row], int]:
        """k nearest chunks with optional metadata filters.

        Filters are applied in SQL WHERE clause before ranking by distance.
        Returns both the top-k results and total candidates evaluated (pre-k-limit).
        """
        distance = ChunkRow.embedding.cosine_distance(query_vector)
        filters = []

        if chunk_types:
            filters.append(ChunkRow.chunk_type.in_(chunk_types))
        if sector is not None:
            filters.append(ChunkRow.metadata_["client_sector"].astext == sector)
        if year_from is not None or year_to is not None:
            year_str = ChunkRow.metadata_["year"].astext.cast(int)
            if year_from is not None:
                filters.append(year_str >= year_from)
            if year_to is not None:
                filters.append(year_str <= year_to)

        stmt = (
            select(
                ChunkRow.id,
                ChunkRow.document_id,
                ChunkRow.chunk_type,
                ChunkRow.content,
                ChunkRow.metadata_,
                distance.label("distance"),
            )
            .order_by(distance)
        )

        if filters:
            stmt = stmt.where(*filters)

        # Get all matching candidates to report candidates_evaluated
        all_matching = list((await session.execute(stmt)).all())
        candidates_evaluated = len(all_matching)

        # Apply k-limit for final results
        filtered_results = all_matching[:k]
        return (filtered_results, candidates_evaluated)
