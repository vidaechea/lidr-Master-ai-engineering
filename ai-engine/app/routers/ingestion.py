from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_catalog, get_filesystem_loader, get_parser_registry
from app.ingestion.catalog.models import CatalogDecision, DataCatalog
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.orchestrator import ingest_source
from app.ingestion.parsers.registry import ParserRegistry
from app.persistence.database import SessionLocal, get_session
from app.persistence.repositories.jobs import JobsRepository
from app.schemas.ingestion import IngestionJobView, IngestionRunRequest, IngestionRunResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _run_in_background(
    *,
    job_id: uuid.UUID,
    source_name: str,
    catalog: DataCatalog,
    loader: FileSystemLoader,
    registry: ParserRegistry,
) -> None:
    session = SessionLocal()
    try:
        repo = JobsRepository(session)
        ingest_source(
            catalog=catalog,
            source_name=source_name,
            loader=loader,
            registry=registry,
            jobs_repo=repo,
            job_id=job_id,
        )
    except Exception as exc:
        log.error(
            "ingestion_background_failed",
            job_id=str(job_id),
            source_name=source_name,
            error=str(exc)[:400],
        )
    finally:
        session.close()


@router.post(
    "/runs",
    status_code=202,
    responses={400: {"description": "Source is not allowed"}, 404: {"description": "Source not found"}},
)
def create_ingestion_run(
    request: IngestionRunRequest,
    background: BackgroundTasks,
    session: Annotated[Session, Depends(get_session)],
    catalog: Annotated[DataCatalog, Depends(get_catalog)],
    loader: Annotated[FileSystemLoader, Depends(get_filesystem_loader)],
    registry: Annotated[ParserRegistry, Depends(get_parser_registry)],
) -> IngestionRunResponse:
    source = catalog.find(request.source_name)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail={"reason": "unknown_source", "source_name": request.source_name},
        )
    if source.decision is not CatalogDecision.INCLUDE:
        raise HTTPException(
            status_code=400,
            detail={
                "reason": "source_not_included",
                "source_name": request.source_name,
                "decision": source.decision.value,
                "decision_reason": source.decision_reason,
            },
        )

    repo = JobsRepository(session)
    job = repo.create(source_name=request.source_name)

    background.add_task(
        _run_in_background,
        job_id=job.job_id,
        source_name=request.source_name,
        catalog=catalog,
        loader=loader,
        registry=registry,
    )
    return IngestionRunResponse(job_id=job.job_id, source_name=job.source_name, status=job.status)


@router.get(
    "/jobs/{job_id}",
    responses={404: {"description": "Job not found"}},
)
def get_ingestion_job(
    job_id: uuid.UUID,
    session: Annotated[Session, Depends(get_session)],
) -> IngestionJobView:
    job = JobsRepository(session).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return IngestionJobView(
        job_id=job.job_id,
        source_name=job.source_name,
        status=job.status,
        documents_count=job.documents_count,
        error_message=job.error_message,
        started_at=job.started_at,
        finished_at=job.finished_at,
    )
