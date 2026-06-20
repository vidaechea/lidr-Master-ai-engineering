from __future__ import annotations

import uuid

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status

from app.dependencies import DbDep, CurrentUser
from app.schemas.estimation import (
    AsyncEstimationOut,
    CacheMetricsOut,
    ChunkingComparisonIn,
    ChunkingComparisonOut,
    EstimationCreate,
    EstimationListItem,
    EstimationOut,
    OutputFormat,
    SemanticSearchIn,
    SemanticSearchOut,
    RuntimeModelsOut,
    RuntimeModelsUpdateIn,
    SessionCreateResponse,
    SessionEstimationOut,
    SessionStateOut,
)
from app.services import ai_client, estimation_service, rag_lab_service

router = APIRouter(prefix="/estimations", tags=["estimations"])


@router.get("/cache/metrics", response_model=CacheMetricsOut)
async def get_cache_metrics(current_user: CurrentUser):
    """Return cache metrics from the AI engine for the authenticated user."""
    _ = current_user
    payload = await ai_client.get_cache_metrics()
    return CacheMetricsOut(**payload)


@router.get("/config/models", response_model=RuntimeModelsOut)
async def get_runtime_models(current_user: CurrentUser):
    """Return current runtime model configuration from the AI engine."""
    _ = current_user
    payload = await ai_client.get_runtime_models()
    return RuntimeModelsOut(**payload)


@router.put("/config/models", response_model=RuntimeModelsOut)
async def update_runtime_models(body: RuntimeModelsUpdateIn, current_user: CurrentUser):
    """Update runtime model overrides in the AI engine."""
    _ = current_user
    payload = await ai_client.update_runtime_models(body.models)
    return RuntimeModelsOut(**payload)


@router.post("/rag/chunking-comparison", response_model=ChunkingComparisonOut)
async def compare_chunking(body: ChunkingComparisonIn, current_user: CurrentUser):
    """Run chunking comparison over the bundled sample budgets corpus."""
    _ = current_user
    budgets = rag_lab_service.load_sample_budgets()
    payload = await ai_client.compare_chunking(
        {
            "budgets": budgets,
            "queries": body.queries,
            "strategies": body.strategies,
            "top_k": body.top_k,
        }
    )
    return ChunkingComparisonOut(**payload)


@router.post("/search", response_model=SemanticSearchOut)
async def search_semantic(body: SemanticSearchIn, current_user: CurrentUser):
    """Proxy semantic search using the feature-flagged public AI Engine contract."""
    _ = current_user
    payload = await ai_client.search_semantic(body.model_dump())
    return SemanticSearchOut(**payload)


@router.post("/embeddings/search", response_model=SemanticSearchOut)
async def search_semantic_legacy(body: SemanticSearchIn, current_user: CurrentUser):
    """Legacy semantic search route kept for gradual migration of consumers."""
    _ = current_user
    payload = await ai_client.search_semantic(body.model_dump(), use_public_contract=False)
    return SemanticSearchOut(**payload)


@router.post("/sessions", response_model=SessionCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation_session(current_user: CurrentUser):
    """Create a conversational session in the AI engine (auth required)."""
    _ = current_user
    payload = await ai_client.create_session()
    return SessionCreateResponse(**payload)


@router.get("/sessions/{session_id}", response_model=SessionStateOut)
async def get_conversation_session_state(session_id: str, current_user: CurrentUser):
    """Fetch current history + project metadata for a conversational session."""
    _ = current_user
    payload = await ai_client.get_session_state(session_id)
    return SessionStateOut(**payload)


@router.post("/sessions/{session_id}/estimate", response_model=SessionEstimationOut)
async def create_conversation_estimation(
    session_id: str,
    current_user: CurrentUser,
    transcript: Annotated[str, Form(min_length=20)],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
    model: Annotated[str | None, Form()] = None,
    temperature: Annotated[float | None, Form(ge=0.0, le=2.0)] = None,
    pre_call: Annotated[bool, Form()] = False,
    output_format: Annotated[OutputFormat, Form()] = "phases_table",
    prompt_version: Annotated[str, Query()] = "v1",
):
    """Proxy multipart conversational estimation to the AI engine sessions API."""
    _ = current_user

    form_fields: dict[str, str] = {
        "transcript": transcript,
        "pre_call": str(pre_call).lower(),
        "output_format": output_format,
    }
    if model:
        form_fields["model"] = model
    if temperature is not None:
        form_fields["temperature"] = str(temperature)

    proxy_files: list[tuple[str, tuple[str, bytes, str]]] = []
    for upload in attachments or []:
        content = await upload.read()
        proxy_files.append(
            (
                "attachments",
                (
                    upload.filename or "attachment.bin",
                    content,
                    upload.content_type or "application/octet-stream",
                ),
            )
        )

    payload = await ai_client.estimate_session_multipart(
        session_id=session_id,
        form_fields=form_fields,
        files=proxy_files,
        prompt_version=prompt_version,
    )
    return SessionEstimationOut(**payload)


@router.get("", response_model=list[EstimationListItem])
async def list_estimations(
    current_user: CurrentUser,
    db: DbDep,
    project_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    return await estimation_service.list_estimations(
        db, current_user.id, project_id, status_filter, limit, offset
    )


@router.post("", response_model=EstimationOut, status_code=status.HTTP_201_CREATED)
async def create_estimation(body: EstimationCreate, current_user: CurrentUser, db: DbDep):
    """Synchronous estimation — waits for the AI Engine to complete."""
    return await estimation_service.create_and_run_sync(db, current_user.id, body)


@router.post("/async", response_model=AsyncEstimationOut, status_code=status.HTTP_202_ACCEPTED)
async def create_estimation_async(
    body: EstimationCreate, current_user: CurrentUser, db: DbDep, request: Request
):
    """Async estimation via Redis queue — returns immediately with a job_id."""
    base_url = str(request.base_url).rstrip("/")
    estimation, job_id = await estimation_service.create_async(
        db, current_user.id, body, base_url
    )
    return AsyncEstimationOut(
        estimation_id=estimation.id,
        job_id=job_id,
        status=estimation.status,
    )


@router.get("/{estimation_id}", response_model=EstimationOut, responses={404: {"detail": "Estimation not found"}})
async def get_estimation(estimation_id: uuid.UUID, current_user: CurrentUser, db: DbDep):
    estimation = await estimation_service.get_estimation(db, estimation_id, current_user.id)
    if not estimation:
        raise HTTPException(status_code=404, detail="Estimation not found")
    return estimation


@router.get("/{estimation_id}/status", responses={404: {"detail": "Estimation not found"}})
async def get_estimation_status(
    estimation_id: uuid.UUID, current_user: CurrentUser, db: DbDep
):
    """Lightweight polling endpoint for async estimations."""
    estimation = await estimation_service.get_estimation(db, estimation_id, current_user.id)
    if not estimation:
        raise HTTPException(status_code=404, detail="Estimation not found")
    return {
        "id": estimation.id,
        "status": estimation.status,
        "completed_at": estimation.completed_at,
    }
