from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.sql import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.generation.rag.analysis.comparison import ChunkingComparator, DEFAULT_STRATEGIES
from app.generation.rag.chunking.strategies.advanced import (
    ContextualRetrievalBudgetChunker,
    HierarchicalBudgetChunker,
    PropositionalBudgetChunker,
    RecursiveBudgetChunker,
    SemanticBudgetChunker,
    SentenceWindowBudgetChunker,
)
from app.generation.rag.chunking.strategies.fixed_size import FixedSizeBudgetChunker
from app.generation.rag.chunking.structural import JSONStructuralChunker, chunk_text
from app.generation.rag.embedding.embedder import EMBEDDING_DIMENSION, EMBEDDING_MODEL, embed_texts
from app.generation.rag.schemas import (
    Budget,
    CompareRequest,
    CompareResponse,
    ChunkItem,
    ChunkRequest,
    ChunkResponse,
    EmbedRequest,
    EmbedResponse,
    EmbeddingItem,
    IngestPersistRequest,
    IngestPersistResponse,
    SearchRequest,
    SearchResponse,
    SearchResultItem,
)
from app.persistence.database import get_async_session
from app.persistence.models import ChunkRow, DocumentRow

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/embedding-pipeline", tags=["embedding-pipeline"])
ingest_router = APIRouter(tags=["embeddings"])
public_search_router = APIRouter(tags=["search"])


_AVAILABLE_CHUNKERS = {
    "structural": JSONStructuralChunker,
    "fixed_size": FixedSizeBudgetChunker,
    "recursive": RecursiveBudgetChunker,
    "sentence_window": SentenceWindowBudgetChunker,
    "semantic": SemanticBudgetChunker,
    "propositional": PropositionalBudgetChunker,
    "contextual_retrieval": ContextualRetrievalBudgetChunker,
    "hierarchical": HierarchicalBudgetChunker,
}

_INTERNAL_ERROR_MSG = "Internal processing error"


@router.post("/chunks", responses={400: {"description": "Invalid chunk parameters"}})
def build_chunks(payload: ChunkRequest) -> ChunkResponse:
    try:
        chunks = chunk_text(
            text=payload.text,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ChunkResponse(chunks=[ChunkItem(index=i, text=chunk) for i, chunk in enumerate(chunks)])


@router.post("/embeddings", responses={400: {"description": "Invalid embedding parameters"}, 500: {"description": _INTERNAL_ERROR_MSG}})
def build_embeddings(payload: EmbedRequest) -> EmbedResponse:
    texts = [item.strip() for item in payload.texts if item and item.strip()]
    if not texts:
        raise HTTPException(status_code=400, detail="At least one non-empty text is required")

    try:
        vectors = embed_texts(texts=texts, model=payload.model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("embedding_generation_failed", error=str(exc)[:400], model=payload.model)
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR_MSG) from exc

    items = [EmbeddingItem(index=i, vector=vector) for i, vector in enumerate(vectors)]
    return EmbedResponse(model=payload.model, embeddings=items)


@ingest_router.post(
    "/compare",
    response_model=CompareResponse,
    responses={400: {"description": "Unknown strategy"}, 500: {"description": _INTERNAL_ERROR_MSG}},
)
def compare_chunking(payload: CompareRequest) -> CompareResponse:
    strategy_names = payload.strategies or list(DEFAULT_STRATEGIES)
    unknown = [name for name in strategy_names if name not in _AVAILABLE_CHUNKERS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {unknown[0]}")

    try:
        comparator = ChunkingComparator(
            {name: _AVAILABLE_CHUNKERS[name]() for name in strategy_names}
        )
        stats = comparator.compute_stats(payload.budgets)
        queries = comparator.run_queries(payload.budgets, payload.queries, payload.top_k)
        return CompareResponse(stats_per_strategy=stats, queries_per_strategy=queries)
    except ValueError as exc:
        log.warning("chunking_compare_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("chunking_compare_failed", error=str(exc)[:400])
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR_MSG) from exc


# ============================================================================
# Ingest endpoint: Chunk + Embed budgets
# ============================================================================


@ingest_router.post(
    "/ingest",
    response_model=IngestPersistResponse,
    responses={
        200: {"description": "Successfully ingested and persisted document chunks"},
        409: {"description": "Document already ingested"},
        400: {"description": "Validation error in chunker or embedder"},
        422: {"description": "Validation error in request schema"},
        500: {"description": f"{_INTERNAL_ERROR_MSG} (e.g., OpenAI API failure)"},
    },
)
async def ingest(
    payload: IngestPersistRequest,
    session: AsyncSession = Depends(get_async_session),
) -> IngestPersistResponse:
    """
    Ingest one document and persist its chunks+embeddings in a single transaction.
    """
    start_time = time.perf_counter()

    try:
        budget = Budget.model_validate(payload.content)
        document_id: int | None = None
        chunks_created = 0
        embedding_dimension = EMBEDDING_DIMENSION

        async with session.begin():
            existing_document_id = (
                await session.execute(
                    select(DocumentRow.id).where(DocumentRow.source_path == payload.source_path)
                )
            ).scalar_one_or_none()
            if existing_document_id is not None:
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "Document already ingested",
                        "document_id": int(existing_document_id),
                    },
                )

            document = DocumentRow(
                source_path=payload.source_path,
                document_type=payload.document_type,
                metadata_json={},
            )
            session.add(document)
            await session.flush()
            document_id = int(document.id)

            chunker = JSONStructuralChunker()
            chunks = chunker.chunk([budget])
            vectors = embed_texts(texts=[chunk.text for chunk in chunks], model=EMBEDDING_MODEL)

            if len(vectors) != len(chunks):
                raise ValueError("Embedding count does not match generated chunks")

            chunk_rows = [
                ChunkRow(
                    document_id=document.id,
                    chunk_type="budget_component",
                    content=chunk.text,
                    embedding=vector,
                    metadata_json=chunk.metadata,
                )
                for chunk, vector in zip(chunks, vectors)
            ]
            session.add_all(chunk_rows)
            chunks_created = len(chunk_rows)
            embedding_dimension = len(vectors[0]) if vectors else EMBEDDING_DIMENSION

        log.info(
            "ingest_completed",
            source_path=payload.source_path,
            document_id=document_id,
            chunks_created=chunks_created,
        )

        ingestion_time_ms = int((time.perf_counter() - start_time) * 1000)

        return IngestPersistResponse(
            document_id=document_id or 0,
            chunks_created=chunks_created,
            embedding_dimension=embedding_dimension,
            ingestion_time_ms=ingestion_time_ms,
        )

    except ValidationError as exc:
        log.warning("ingest_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail="Invalid budget content") from exc
    except ValueError as exc:
        # Validation errors from chunker or embedder
        log.warning("ingest_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # OpenAI API errors, network issues, etc. — generic message to client
        log.error("ingest_failed", error=str(exc)[:400])
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR_MSG) from exc


async def _execute_semantic_search(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_async_session),
) -> SearchResponse:
    """Execute semantic nearest-neighbor search over persisted chunks."""
    start_time = time.perf_counter()

    try:
        vectors = embed_texts(texts=[payload.query], model=EMBEDDING_MODEL)
        if not vectors:
            raise ValueError("Failed to generate query embedding")
        query_vector = vectors[0]

        distance_expr = ChunkRow.embedding.cosine_distance(query_vector)
        stmt: Select = (
            select(
                ChunkRow.id,
                ChunkRow.document_id,
                ChunkRow.chunk_type,
                ChunkRow.content,
                ChunkRow.metadata_json.label("metadata"),
                distance_expr.label("distance"),
            )
            .where(ChunkRow.embedding.is_not(None))
            .order_by(distance_expr)
            .limit(payload.k)
        )

        db_result = await session.execute(stmt)
        rows = db_result.all()

        response_rows = [
            SearchResultItem(
                chunk_id=int(row.id),
                document_id=int(row.document_id),
                chunk_type=row.chunk_type,
                content=row.content,
                distance=float(row.distance),
                metadata=row.metadata or {},
            )
            for row in rows
        ]

        search_time_ms = int((time.perf_counter() - start_time) * 1000)

        return SearchResponse(
            query=payload.query,
            k=payload.k,
            search_time_ms=search_time_ms,
            results=response_rows,
        )
    except ValueError as exc:
        log.warning("search_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("search_failed", error=str(exc)[:400])
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR_MSG) from exc


@ingest_router.post(
    "/search",
    response_model=SearchResponse,
    responses={
        400: {"description": "Invalid semantic search query"},
        500: {"description": _INTERNAL_ERROR_MSG},
    },
)
async def search(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_async_session),
) -> SearchResponse:
    """Compatibility route for semantic nearest-neighbor search."""
    return await _execute_semantic_search(payload, session)


@public_search_router.post(
    "/search",
    response_model=SearchResponse,
    responses={
        400: {"description": "Invalid semantic search query"},
        500: {"description": _INTERNAL_ERROR_MSG},
    },
)
async def public_search(
    payload: SearchRequest,
    session: AsyncSession = Depends(get_async_session),
) -> SearchResponse:
    """Public semantic search contract matching the dedicated /search endpoint."""
    return await _execute_semantic_search(payload, session)


