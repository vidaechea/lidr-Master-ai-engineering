from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from app.generation.rag.chunking.structural import JSONStructuralChunker, chunk_text
from app.generation.rag.embedding.embedder import OpenAIEmbedder, embed_texts
from app.generation.rag.schemas import (
    ChunkItem,
    ChunkRequest,
    ChunkResponse,
    EmbedRequest,
    EmbedResponse,
    EmbeddingItem,
    IngestRequest,
    IngestResponse,
    IngestStats,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/embedding-pipeline", tags=["embedding-pipeline"])
ingest_router = APIRouter(tags=["embeddings"])


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


@router.post("/embeddings", responses={400: {"description": "Invalid embedding parameters"}, 500: {"description": "Internal processing error"}})
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
        raise HTTPException(status_code=500, detail="Internal processing error") from exc

    items = [EmbeddingItem(index=i, vector=vector) for i, vector in enumerate(vectors)]
    return EmbedResponse(model=payload.model, embeddings=items)


# ============================================================================
# Ingest endpoint: Chunk + Embed budgets
# ============================================================================


@ingest_router.post(
    "/ingest",
    responses={
        200: {"description": "Successfully ingested and embedded budgets"},
        400: {"description": "Validation error in chunker or embedder"},
        422: {"description": "Validation error in request schema"},
        500: {"description": "Internal processing error (e.g., OpenAI API failure)"},
    },
)
def ingest(payload: IngestRequest) -> IngestResponse:
    """
    Ingest a list of budgets: chunk them and generate embeddings.

    Orchestrates:
    1. Chunk budgets into components (JSONStructuralChunker)
    2. Embed chunks (OpenAIEmbedder)
    3. Aggregate statistics

    Returns:
    - 200: IngestResponse with embedded chunks and statistics
    - 422: Pydantic validation error (automatic)
    - 500: OpenAI API error with generic message to client
    """
    try:
        # Instantiate services
        chunker = JSONStructuralChunker()
        embedder = OpenAIEmbedder()

        # Chunk budgets into components
        chunks = chunker.chunk(payload.budgets)

        # Embed chunks
        embedded_chunks = embedder.embed_many(chunks)

        # Calculate aggregated statistics
        total_tokens = sum(chunk.token_count for chunk in embedded_chunks)
        estimated_cost = embedder._calculate_cost(total_tokens)

        stats = IngestStats(
            total_budgets=len(payload.budgets),
            total_chunks=len(embedded_chunks),
            total_tokens=total_tokens,
            estimated_cost_usd=round(estimated_cost, 6),
        )

        log.info(
            "ingest_completed",
            total_budgets=len(payload.budgets),
            total_chunks=len(embedded_chunks),
            total_tokens=total_tokens,
            estimated_cost_usd=round(estimated_cost, 6),
        )

        return IngestResponse(chunks=embedded_chunks, stats=stats)

    except ValueError as exc:
        # Validation errors from chunker or embedder
        log.warning("ingest_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # OpenAI API errors, network issues, etc. — generic message to client
        log.error("ingest_failed", error=str(exc)[:400])
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


