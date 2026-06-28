"""Async data-access layer for the vector store.

The store never opens or commits sessions: the caller (ingest service,
retriever) owns the ``AsyncSession`` so a whole ingest — duplicate check,
document row, chunk rows — fits in ONE transaction. A failure anywhere rolls
everything back and leaves no orphan ``documents`` row.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import Row, desc, func, literal_column, select
from sqlalchemy.dialects.postgresql import TSVECTOR
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

    async def search_hybrid(
        self,
        session: AsyncSession,
        *,
        query_text: str,
        query_vector: list[float],
        k: int,
        rrf_k: int,
        per_branch_k: int,
    ) -> tuple[list[Row], int]:
        """Hybrid retrieval: vector branch + lexical branch fused with RRF."""
        return await self.search_hybrid_with_filters(
            session,
            query_text=query_text,
            query_vector=query_vector,
            k=k,
            rrf_k=rrf_k,
            per_branch_k=per_branch_k,
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
        filters = self._build_filters(
            sector=sector,
            year_from=year_from,
            year_to=year_to,
            chunk_types=chunk_types,
        )

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

        all_matching = list((await session.execute(stmt)).all())
        candidates_evaluated = len(all_matching)
        filtered_results = all_matching[:k]
        return (filtered_results, candidates_evaluated)

    async def search_hybrid_with_filters(
        self,
        session: AsyncSession,
        *,
        query_text: str,
        query_vector: list[float],
        k: int,
        rrf_k: int,
        per_branch_k: int,
        sector: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        chunk_types: list[str] | None = None,
    ) -> tuple[list[Row], int]:
        """Hybrid retrieval with metadata filters and RRF score fusion."""
        filters = self._build_filters(
            sector=sector,
            year_from=year_from,
            year_to=year_to,
            chunk_types=chunk_types,
        )

        vector_rows, vector_candidates = await self._search_vector_rows(
            session,
            query_vector=query_vector,
            filters=filters,
        )
        lexical_rows, lexical_candidates = await self._search_lexical_rows(
            session,
            query_text=query_text,
            filters=filters,
        )

        fused_rows = self._rrf_fuse_rows(
            vector_rows=vector_rows[:per_branch_k],
            lexical_rows=lexical_rows[:per_branch_k],
            k=k,
            rrf_k=rrf_k,
        )
        candidates_evaluated = len({row.id for row in vector_rows}.union({row.id for row in lexical_rows}))
        if candidates_evaluated == 0:
            candidates_evaluated = max(vector_candidates, lexical_candidates)
        return fused_rows, candidates_evaluated

    @staticmethod
    def _build_filters(
        *,
        sector: str | None,
        year_from: int | None,
        year_to: int | None,
        chunk_types: list[str] | None,
    ) -> list:
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

        return filters

    async def _search_vector_rows(
        self,
        session: AsyncSession,
        *,
        query_vector: list[float],
        filters: list,
    ) -> tuple[list[Row], int]:
        distance = ChunkRow.embedding.cosine_distance(query_vector)

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

        all_matching = list((await session.execute(stmt)).all())
        return all_matching, len(all_matching)

    async def _search_lexical_rows(
        self,
        session: AsyncSession,
        *,
        query_text: str,
        filters: list,
    ) -> tuple[list[Row], int]:
        content_tsv = literal_column("content_tsv", type_=TSVECTOR)
        ts_query = func.plainto_tsquery("spanish", query_text)
        rank = func.ts_rank_cd(content_tsv, ts_query)
        lexical_distance = (1.0 - func.least(rank, 1.0)).label("distance")

        stmt = (
            select(
                ChunkRow.id,
                ChunkRow.document_id,
                ChunkRow.chunk_type,
                ChunkRow.content,
                ChunkRow.metadata_,
                lexical_distance,
            )
            .where(content_tsv.bool_op("@@")(ts_query))
            .order_by(desc(rank), ChunkRow.id)
        )
        if filters:
            stmt = stmt.where(*filters)

        all_matching = list((await session.execute(stmt)).all())
        return all_matching, len(all_matching)

    @staticmethod
    def _rrf_fuse_rows(
        *,
        vector_rows: list[Row],
        lexical_rows: list[Row],
        k: int,
        rrf_k: int,
    ) -> list[Row]:
        if not vector_rows and not lexical_rows:
            return []

        row_by_id: dict[int, Row] = {}
        # Prefer vector row details for shared ids to preserve cosine distance.
        for row in lexical_rows:
            row_by_id[row.id] = row
        for row in vector_rows:
            row_by_id[row.id] = row

        fused_scores: dict[int, float] = defaultdict(float)
        best_rank: dict[int, int] = {}

        for rank, row in enumerate(vector_rows, start=1):
            fused_scores[row.id] += 1.0 / (rrf_k + rank)
            best_rank[row.id] = min(best_rank.get(row.id, rank), rank)

        for rank, row in enumerate(lexical_rows, start=1):
            fused_scores[row.id] += 1.0 / (rrf_k + rank)
            best_rank[row.id] = min(best_rank.get(row.id, rank), rank)

        ranked_ids = sorted(
            fused_scores,
            key=lambda item_id: (-fused_scores[item_id], best_rank[item_id], item_id),
        )
        return [row_by_id[item_id] for item_id in ranked_ids[:k]]
