from __future__ import annotations

import time

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.generation.rag.chunking.structural import JSONStructuralChunker, chunk_text
from app.generation.rag.embedding.embedder import EMBEDDING_DIMENSION, EMBEDDING_MODEL, embed_texts
from app.generation.rag.schemas import (
    Budget,
    ChunkItem,
    ChunkRequest,
    ChunkResponse,
    EmbedRequest,
    EmbedResponse,
    EmbeddingItem,
    IngestPersistRequest,
    IngestPersistResponse,
)
from app.persistence.database import get_async_session
from app.persistence.models import ChunkRow, DocumentRow

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
    response_model=IngestPersistResponse,
    responses={
        200: {"description": "Successfully ingested and persisted document chunks"},
        409: {"description": "Document already ingested"},
        400: {"description": "Validation error in chunker or embedder"},
        422: {"description": "Validation error in request schema"},
        500: {"description": "Internal processing error (e.g., OpenAI API failure)"},
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

        budget = Budget.model_validate(payload.content)
        document_id: int | None = None
        chunks_created = 0
        embedding_dimension = EMBEDDING_DIMENSION

        async with session.begin():
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
        raise HTTPException(status_code=500, detail="Internal processing error") from exc


