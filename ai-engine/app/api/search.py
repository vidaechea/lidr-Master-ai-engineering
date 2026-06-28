"""Semantic search endpoint (Session 8)."""

from __future__ import annotations

from typing import Annotated
import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_semantic_retriever
from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.schemas import SearchRequest, SearchResponse

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "",
    responses={
        400: {"description": "Invalid search parameters"},
        500: {"description": "Internal error during retrieval"},
    },
)
async def search(
    payload: SearchRequest,
    retriever: Annotated[SemanticRetriever, Depends(get_semantic_retriever)],
) -> SearchResponse:
    """Search for semantically similar chunks by cosine distance.

    **Query Embedding**: The query is embedded with the same model used during ingest
    (text-embedding-3-small). Mixing embedding models breaks distance semantics.

    **Ranking**: Results are ranked by cosine distance. Lower distance = higher similarity.

    **No Vector Index (Baseline)**: This query uses a sequential scan against all chunks
    to establish the baseline performance. The live session adds an HNSW index and
    measures the speedup.
    """
    try:
        response = await retriever.search(
            query=payload.query,
            k=payload.k,
            mode=payload.mode,
            rerank=payload.rerank,
        )
        return response
    except Exception as exc:
        log.error("search_failed", error=str(exc)[:400], query=payload.query[:80])
        raise HTTPException(status_code=500, detail="Internal retrieval error") from exc
