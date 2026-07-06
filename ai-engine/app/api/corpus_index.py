from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_chunk_store, get_corpus_index_service
from app.foundation.persistence.database import SessionLocal, get_session
from app.foundation.persistence.repositories.jobs import JobsRepository
from app.generation.rag.index_service import CorpusIndexService
from app.generation.rag.schemas import (
    CollectionStats,
    CorpusStats,
    IndexJobView,
    IndexRunRequest,
    IndexRunResponse,
)
from app.generation.rag.store.repository import ChunkStore

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/embeddings", tags=["corpus-index"])


def _job_update(fn: Callable[[JobsRepository], None]) -> None:
    session = SessionLocal()
    try:
        fn(JobsRepository(session))
    finally:
        session.close()


async def _run_expansion(
    *,
    job_id: uuid.UUID,
    documents,
    document_type: str,
    chunk_type: str,
    service: CorpusIndexService,
) -> None:
    _job_update(lambda repo: repo.mark_running(job_id))
    try:
        result = await service.expand(
            documents,
            document_type=document_type,
            chunk_type=chunk_type,
            on_progress=lambda processed: _job_update(
                lambda repo: repo.set_documents_count(job_id, processed)
            ),
        )
        _job_update(
            lambda repo: repo.mark_completed(
                job_id,
                documents_count=result.documents_indexed + result.documents_skipped,
            )
        )
    except Exception as exc:
        message = str(exc)
        log.error("corpus_expansion_failed", job_id=str(job_id), error=message[:400])
        _job_update(lambda repo: repo.mark_failed(job_id, error_message=message))


@router.post(
    "/index/runs",
    status_code=202,
    responses={500: {"description": "Embedding service is not available"}},
)
def create_index_run(
    request: IndexRunRequest,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    service: Annotated[CorpusIndexService | None, Depends(get_corpus_index_service)],
) -> IndexRunResponse:
    if service is None:
        raise HTTPException(status_code=500, detail="Embedding service is not available.")

    job = JobsRepository(session).create(source_name=f"corpus-expansion:{request.chunk_type}")
    background.add_task(
        _run_expansion,
        job_id=job.job_id,
        documents=request.documents,
        document_type=request.document_type,
        chunk_type=request.chunk_type,
        service=service,
    )
    return IndexRunResponse(
        job_id=job.job_id,
        documents_total=len(request.documents),
        status=job.status,
    )


@router.get(
    "/index/jobs/{job_id}",
    responses={404: {"description": "job not found"}},
)
def get_index_job(
    job_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> IndexJobView:
    job = JobsRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IndexJobView(
        job_id=job.job_id,
        status=job.status,
        documents_processed=job.documents_count,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )


@router.get("/index/stats")
async def get_corpus_stats(
    store: Annotated[ChunkStore, Depends(get_chunk_store)],
) -> CorpusStats:
    rows = await store.corpus_stats()
    collections = [
        CollectionStats(
            collection=collection,
            documents=documents,
            chunks=chunks,
            hnsw_indexed=hnsw_indexed,
        )
        for collection, documents, chunks, hnsw_indexed in rows
    ]
    return CorpusStats(
        collections=collections,
        total_chunks=sum(item.chunks for item in collections),
    )