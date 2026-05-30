from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException

from app.embedding_pipeline.chunker import chunk_text
from app.embedding_pipeline.embedder import embed_texts
from app.embedding_pipeline.schemas import (
    ChunkItem,
    ChunkRequest,
    ChunkResponse,
    EmbedRequest,
    EmbedResponse,
    EmbeddingItem,
)

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/embedding-pipeline", tags=["embedding-pipeline"])


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
