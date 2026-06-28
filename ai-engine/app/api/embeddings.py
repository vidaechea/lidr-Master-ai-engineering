from __future__ import annotations

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError

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
from app.generation.rag.embedding.embedder import embed_texts
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
)
from app.dependencies import get_rag_ingest_service, get_runtime_config, get_semantic_retriever
from app.generation.rag.ingest_service import RagIngestService, DuplicateDocumentError
from app.foundation.llm.runtime_config import RuntimeModelConfig
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/embedding-pipeline", tags=["embedding-pipeline"])
ingest_router = APIRouter(tags=["embeddings"])


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
    responses={400: {"description": "Unknown strategy"}, 500: {"description": _INTERNAL_ERROR_MSG}},
)
async def compare_chunking(
    payload: CompareRequest,
    runtime_config: Annotated[RuntimeModelConfig, Depends(get_runtime_config)],
) -> CompareResponse:
    strategy_names = payload.strategies or list(DEFAULT_STRATEGIES)
    unknown = [name for name in strategy_names if name not in _AVAILABLE_CHUNKERS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown strategy: {unknown[0]}")

    try:
        propositional_model = await runtime_config.effective("PROPOSITIONAL_CHUNKER_MODEL")
        contextual_model = await runtime_config.effective("CONTEXTUAL_CHUNKER_MODEL")

        chunkers = {}
        for name in strategy_names:
            if name == "propositional":
                chunkers[name] = PropositionalBudgetChunker(model_name=propositional_model)
            elif name == "contextual_retrieval":
                chunkers[name] = ContextualRetrievalBudgetChunker(model_name=contextual_model)
            else:
                chunkers[name] = _AVAILABLE_CHUNKERS[name]()

        comparator = ChunkingComparator(chunkers)
        stats = comparator.compute_stats(payload.budgets)
        queries = comparator.run_queries(payload.budgets, payload.queries, payload.top_k)
        log.info(
            "chunking_compare_runtime_models",
            propositional_chunker_model=propositional_model,
            contextual_chunker_model=contextual_model,
        )
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
    service: Annotated[RagIngestService, Depends(get_rag_ingest_service)],
) -> IngestPersistResponse:
    """
    Ingest one document and persist its chunks+embeddings in a single transaction.
    """

    try:
        budget = Budget.model_validate(payload.content)
        response = await service.ingest(
            source_path=payload.source_path,
            document_type=payload.document_type,
            budget=budget,
        )
        return response

    except DuplicateDocumentError as exc:
        log.warning("ingest_duplicate", source_path=payload.source_path, document_id=exc.document_id)
        return JSONResponse(
            status_code=409,
            content={
                "detail": "Document already ingested",
                "document_id": exc.document_id,
            },
        )

    except ValidationError as exc:
        log.warning("ingest_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail="Invalid budget content") from exc
    except ValueError as exc:
        log.warning("ingest_validation_error", error=str(exc)[:400])
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("ingest_failed", error=str(exc)[:400])
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR_MSG) from exc


@ingest_router.post(
    "/search",
    responses={
        400: {"description": "Invalid semantic search query"},
        500: {"description": _INTERNAL_ERROR_MSG},
    },
)
async def search(
    payload: SearchRequest,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
) -> SearchResponse:
    """Legacy compatibility alias for semantic search.

    Canonical endpoint is ``POST /api/v1/search`` (router in ``app/api/search.py``).
    This route stays for backward compatibility and delegates to the same retriever.
    """
    try:
        return await retriever.search(
            query=payload.query,
            k=payload.k,
            mode=payload.mode,
            rerank=payload.rerank,
        )
    except Exception as exc:
        log.error("search_failed", error=str(exc)[:400], query=payload.query[:80])
        raise HTTPException(status_code=500, detail=_INTERNAL_ERROR_MSG) from exc


