from __future__ import annotations

import re
import time
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Request

from app.config import settings
from app.dependencies import (
    TierDep,
    enforce_rag_pipeline_estimate_security,
    enforce_rag_pipeline_retrieval_security,
    get_semantic_retriever,
)
from app.domain.estimation_service import EstimationService
from app.domain.schemas.estimation import EstimationRequest
from app.generation.rag.citation_validator_service import CitationValidatorService
from app.generation.rag.coherence_repair_service import CoherenceRepairService
from app.generation.rag.reformulation_service import QueryReformulationService
from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.schemas import (
    AssembleStageRequest,
    AssembleStageResponse,
    EstimateModule,
    EstimateTask,
    FullEstimateRequest,
    FullEstimateResponse,
    GenerateStageRequest,
    GenerateStageResponse,
    ReformulateStageRequest,
    ReformulateStageResponse,
    RetrieveStageRequest,
    RetrieveStageResponse,
    RagPipelineEstimate,
)

log = structlog.get_logger(__name__)

retrieval_router = APIRouter(prefix="/rag/retrieval", tags=["rag-retrieval"])
pipeline_router = APIRouter(prefix="/rag/estimate", tags=["rag-estimate"])
stages_router = APIRouter(prefix="/rag/stages", tags=["rag-stages"])


class _IdempotencyStore:
    """Small in-memory TTL cache for idempotent full pipeline calls."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[float, FullEstimateResponse]] = {}

    def get(self, key: str) -> FullEstimateResponse | None:
        now = time.time()
        record = self._entries.get(key)
        if record is None:
            return None
        expires_at, payload = record
        if expires_at <= now:
            self._entries.pop(key, None)
            return None
        return payload

    def put(self, key: str, payload: FullEstimateResponse) -> None:
        expires_at = time.time() + settings.rag_pipeline_idempotency_ttl_seconds
        self._entries[key] = (expires_at, payload)


_idempotency_store = _IdempotencyStore()

# Initialize services
_reformulation_service = QueryReformulationService()
_citation_validator = CitationValidatorService()
_coherence_repair = CoherenceRepairService()


def _reformulate(transcript: str) -> ReformulateStageResponse:
    """Distill transcript into structured query using reformulation service."""
    query = _reformulation_service.reformulate(transcript)
    return ReformulateStageResponse(query=query, used_fallback=False)


async def _retrieve(
    *,
    payload: RetrieveStageRequest,
    retriever: SemanticRetriever,
) -> RetrieveStageResponse:
    """Retrieve chunks matching the query with metadata filters applied in SQL."""
    top_k = payload.top_k or settings.rag_pipeline_retrieval_top_k
    distance_threshold = (
        payload.distance_threshold
        if payload.distance_threshold is not None
        else settings.rag_pipeline_retrieval_distance_threshold
    )

    # Use the new search_with_query method that handles metadata filtering
    retrieval = await retriever.search_with_query(
        query=payload.query,
        k=top_k,
        distance_threshold=distance_threshold,
        mode=payload.mode,
        rerank=payload.rerank,
    )

    return RetrieveStageResponse(retrieval=retrieval)


def _assemble(payload: AssembleStageRequest) -> AssembleStageResponse:
    max_context_tokens = payload.max_context_tokens or settings.rag_pipeline_max_context_tokens
    selected_texts: list[str] = []
    selected_source_ids: list[str] = []
    running_tokens = 0
    truncated = False

    for chunk in payload.retrieval.chunks:
        token_estimate = max(1, len(chunk.content) // 4)
        if running_tokens + token_estimate > max_context_tokens:
            truncated = True
            break
        selected_texts.append(f"[{chunk.source_id}] {chunk.content}")
        selected_source_ids.append(chunk.source_id)
        running_tokens += token_estimate

    context_block = "\n\n".join(selected_texts)
    return AssembleStageResponse(
        context_block=context_block,
        included_source_ids=selected_source_ids,
        token_count_estimate=running_tokens,
        truncated=truncated,
    )


def _to_rag_pipeline_estimate(
    *,
    llm_text: str,
    source_ids: list[str],
    low_confidence: bool,
) -> RagPipelineEstimate:
    tasks = [
        EstimateTask(name="Implementation", engineer_days=5.0),
        EstimateTask(name="Testing and QA", engineer_days=2.0),
    ]
    modules = [
        EstimateModule(
            name="Core delivery",
            engineer_days=sum(task.engineer_days for task in tasks),
            tasks=tasks,
        )
    ]
    assumptions = [
        "Estimate generated with available retrieved context.",
        "Human verification is required before commitment.",
    ]
    summary = _extract_clean_summary(llm_text)

    return RagPipelineEstimate(
        summary=summary,
        estimate_markdown=llm_text or None,
        low_confidence=low_confidence,
        modules=modules,
        assumptions=assumptions,
        sources=source_ids,
    )


def _extract_clean_summary(llm_text: str) -> str:
    """Return a short plain-text summary instead of raw, truncated markdown."""
    if not llm_text or not llm_text.strip():
        return "No estimate generated."

    lines = [line.strip() for line in llm_text.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("|") or re.match(r"^[-:|\s]+$", line):
            continue
        cleaned = re.sub(r"^#{1,6}\s*", "", line).strip()
        cleaned = re.sub(r"^Estimate:\s*", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned).strip()
        if cleaned:
            return cleaned[:220]

    plain_text = re.sub(r"[#*_`>|-]", "", llm_text)
    plain_text = " ".join(plain_text.split())
    return plain_text[:220] if plain_text else "No estimate generated."


async def _generate_with_validation(
    *,
    service: EstimationService,
    llm_request: EstimationRequest,
    tier: TierDep,
    payload: GenerateStageRequest,
    low_confidence: bool,
    retrieved_chunks: list | None = None,
) -> RagPipelineEstimate:
    """Generate and validate estimate in a single attempt."""
    result = await service.estimate(
        llm_request,
        prompt_version=settings.prompt_version,
        tier=tier,
    )
    estimate = _to_rag_pipeline_estimate(
        llm_text=result.estimation,
        source_ids=payload.source_ids,
        low_confidence=low_confidence,
    )

    # Validate coherence
    if not _citation_validator.is_coherent(estimate):
        log.warning("estimate_coherence_failed")
        estimate, repairs = _coherence_repair.repair(estimate)
        log.info("estimate_repaired", repairs=repairs)

    # Validate and repair citations if chunks provided
    if retrieved_chunks:
        estimate, citation_warnings = _citation_validator.validate_citations(
            estimate,
            retrieved_chunks,
        )
        if citation_warnings:
            log.warning("estimate_citation_issues", warnings=citation_warnings)

    return estimate


async def _generate(
    *,
    payload: GenerateStageRequest,
    tier: TierDep,
    low_confidence: bool,
    retrieved_chunks: list | None = None,
    max_retries: int = 2,
) -> GenerateStageResponse:
    """Generate estimate with citation validation, coherence repair, and retry logic."""
    service = EstimationService()
    model = settings.rag_pipeline_generation_model
    last_error: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            llm_request = EstimationRequest(
                transcription=(
                    "Use retrieved context as grounding. If context is insufficient, explicitly say it.\n\n"
                    f"Transcript:\n{payload.transcript}\n\n"
                    f"Retrieved context:\n{payload.context_block}"
                ),
                model=model,
                reasoning_effort=settings.rag_pipeline_generation_reasoning_effort,
                max_output_tokens=settings.rag_pipeline_generation_max_tokens,
                pre_call=False,
            )

            estimate = await _generate_with_validation(
                service=service,
                llm_request=llm_request,
                tier=tier,
                payload=payload,
                low_confidence=low_confidence,
                retrieved_chunks=retrieved_chunks,
            )

            log.info("estimate_generated", attempt=attempt, low_confidence=low_confidence)
            return GenerateStageResponse(estimate=estimate)

        except Exception as e:
            last_error = e
            log.warning(
                "estimate_generation_failed",
                attempt=attempt,
                error=str(e),
                max_retries=max_retries,
            )
            if attempt >= max_retries:
                break

    # All retries exhausted, fall back to minimal estimate
    log.error("estimate_generation_max_retries_exceeded", error=str(last_error))
    estimate = _to_rag_pipeline_estimate(
        llm_text="Estimate generation failed. Manual review required.",
        source_ids=payload.source_ids,
        low_confidence=True,
    )
    return GenerateStageResponse(estimate=estimate)


@retrieval_router.post("")
async def retrieve_only(
    payload: RetrieveStageRequest,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
    _: Annotated[str, Depends(enforce_rag_pipeline_retrieval_security)],
) -> RetrieveStageResponse:
    """RAG retrieval endpoint group with security and rate limiting."""
    return await _retrieve(payload=payload, retriever=retriever)


@stages_router.post("/reformulate")
async def reformulate_stage(
    payload: ReformulateStageRequest,
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> ReformulateStageResponse:
    """Stateless stage 1: transcript to structured query."""
    return _reformulate(payload.transcript)


@stages_router.post("/retrieve")
async def retrieve_stage(
    payload: RetrieveStageRequest,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
    _: Annotated[str, Depends(enforce_rag_pipeline_retrieval_security)],
) -> RetrieveStageResponse:
    """Stateless stage 2: semantic retrieval with metadata post-filtering."""
    return await _retrieve(payload=payload, retriever=retriever)


@stages_router.post("/assemble")
async def assemble_stage(
    payload: AssembleStageRequest,
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> AssembleStageResponse:
    """Stateless stage 3: context assembly with token budget."""
    return _assemble(payload)


@stages_router.post("/generate")
async def generate_stage(
    payload: GenerateStageRequest,
    tier: TierDep,
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> GenerateStageResponse:
    """Stateless stage 4: grounded generation."""
    return await _generate(payload=payload, tier=tier, low_confidence=False)


@pipeline_router.post("")
async def estimate_from_transcript(
    payload: FullEstimateRequest,
    request: Request,
    tier: TierDep,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
    _: Annotated[str, Depends(enforce_rag_pipeline_estimate_security)],
) -> FullEstimateResponse:
    """RAG full orchestration endpoint (stateless request, idempotent key optional)."""
    if payload.idempotency_key:
        cached = _idempotency_store.get(payload.idempotency_key)
        if cached is not None:
            cached.idempotency_hit = True
            return cached

    reformulation = _reformulate(payload.transcript)
    retrieval = await _retrieve(
        payload=RetrieveStageRequest(
            query=reformulation.query,
            top_k=payload.top_k,
            distance_threshold=payload.distance_threshold,
            mode=payload.mode,
            rerank=payload.rerank,
        ),
        retriever=retriever,
    )
    assembly = _assemble(
        AssembleStageRequest(
            transcript=payload.transcript,
            query=reformulation.query,
            retrieval=retrieval.retrieval,
            max_context_tokens=settings.rag_pipeline_max_context_tokens,
        )
    )

    # Ensure generation input always satisfies schema constraints even when
    # retrieval returns no chunks and assembly produces an empty context.
    context_block = assembly.context_block.strip()
    if not context_block:
        context_block = "No retrieved context available."
        log.info("rag_empty_context_fallback", top_k=retrieval.retrieval.top_k)

    low_confidence = (
        retrieval.retrieval.low_confidence
        or len(assembly.included_source_ids) == 0
    )

    generation = await _generate(
        payload=GenerateStageRequest(
            transcript=payload.transcript,
            context_block=context_block,
            source_ids=assembly.included_source_ids,
        ),
        tier=tier,
        low_confidence=low_confidence,
        retrieved_chunks=retrieval.retrieval.chunks,
    )

    response = FullEstimateResponse(
        request_id=getattr(request.state, "request_id", None),
        reformulation=reformulation,
        retrieval=retrieval,
        assembly=assembly,
        generation=generation,
        idempotency_hit=False,
    )

    if payload.idempotency_key:
        _idempotency_store.put(payload.idempotency_key, response)

    return response
