"""FastAPI dependencies for the ai-engine service."""
from __future__ import annotations

from functools import lru_cache
from time import monotonic
from typing import Annotated

import structlog
from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt

from app.config import settings
from app.ingestion.catalog import DataCatalog, load_catalog
from app.ingestion.loaders import FileSystemLoader
from app.ingestion.parsers import ParserRegistry, default_registry
from app.domain.schemas.estimation import UserTier
from openai import OpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.foundation.persistence.database import AsyncSessionLocal
from app.generation.rag.chunking.structural import JSONStructuralChunker
from app.generation.rag.embedding.embedder import OpenAIEmbedder
from app.generation.rag.ingest_service import RagIngestService
from app.generation.rag.reranker import CrossEncoderReranker
from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.store.repository import ChunkStore
from app.foundation.llm.runtime_config import RuntimeModelConfig, RuntimeRetrievalConfig

log = structlog.get_logger(__name__)


class _PerMinuteRateLimiter:
    """Simple in-memory fixed-window limiter keyed by (scope, api_key)."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str], tuple[float, int]] = {}

    def allow(self, *, scope: str, api_key: str, limit: int, window_seconds: int = 60) -> bool:
        now = monotonic()
        bucket_key = (scope, api_key)
        window_start, count = self._buckets.get(bucket_key, (now, 0))

        if now - window_start >= window_seconds:
            self._buckets[bucket_key] = (now, 1)
            return True

        if count >= limit:
            return False

        self._buckets[bucket_key] = (window_start, count + 1)
        return True


_rag_pipeline_rate_limiter = _PerMinuteRateLimiter()


def get_request_tier(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
) -> UserTier:
    """Extract the user tier from the Bearer JWT claim.

    The tier is embedded by the backend in the access token at login time and
    is never accepted as a free client parameter.  The JWT is verified with the
    shared secret so the claim cannot be tampered with.

    Falls back to UserTier.DEVELOPER when:
    - No Authorization header is present (e.g. internal tooling, tests).
    - The token is invalid or missing the tier claim.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return UserTier.DEVELOPER

    token = authorization.removeprefix("Bearer ")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        raw_tier = payload.get("tier", "developer")
        return UserTier(raw_tier)
    except (JWTError, ValueError):
        log.warning("tier_extraction_failed_fallback_to_developer")
        return UserTier.DEVELOPER


TierDep = Annotated[UserTier, Depends(get_request_tier)]


def _enforce_scoped_api_key(*, expected: str | None, provided: str | None) -> str:
    """Validate scoped API key; open in dev when expected key is not configured."""
    if expected:
        if provided != expected:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")
        return provided

    # Local development convenience when security key is not configured.
    return provided or "anonymous"


def get_rag_pipeline_retrieval_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    return _enforce_scoped_api_key(
        expected=settings.rag_pipeline_retrieval_api_key,
        provided=x_api_key,
    )


def get_rag_pipeline_estimate_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> str:
    return _enforce_scoped_api_key(
        expected=settings.rag_pipeline_estimate_api_key,
        provided=x_api_key,
    )


def _enforce_rate_limit(*, scope: str, api_key: str) -> None:
    allowed = _rag_pipeline_rate_limiter.allow(
        scope=scope,
        api_key=api_key,
        limit=settings.rag_pipeline_rate_limit_per_minute,
        window_seconds=60,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )


def enforce_rag_pipeline_retrieval_security(
    api_key: Annotated[str, Depends(get_rag_pipeline_retrieval_api_key)],
) -> str:
    _enforce_rate_limit(scope="rag_pipeline_retrieval", api_key=api_key)
    return api_key


def enforce_rag_pipeline_estimate_security(
    api_key: Annotated[str, Depends(get_rag_pipeline_estimate_api_key)],
) -> str:
    _enforce_rate_limit(scope="rag_pipeline_estimate", api_key=api_key)
    return api_key


@lru_cache
def get_catalog() -> DataCatalog:
    return load_catalog(settings.catalog_path)


@lru_cache
def get_filesystem_loader() -> FileSystemLoader:
    return FileSystemLoader(data_root=settings.ingestion_data_root)


@lru_cache
def get_parser_registry() -> ParserRegistry:
    return default_registry()


def build_pseudonymizer(session):
    from app.ingestion.pii import (
        ConsistentPseudonymizer,
        PostgresMappingStore,
        build_analyzer,
    )

    return ConsistentPseudonymizer(
        analyzer=build_analyzer(),
        mapping_store=PostgresMappingStore(session),
        salt=settings.pseudonym_hash_salt,
        faker_locale=settings.pseudonym_faker_locale,
        language="es",
    )


# ============================================================================
# Phase 2: RAG Pipeline Factories (Session 8)
# ============================================================================


@lru_cache
def get_openai_client() -> OpenAI:
    """Singleton OpenAI client for embeddings and LLM calls."""
    return OpenAI(api_key=settings.openai_api_key)


@lru_cache
def get_embedder() -> OpenAIEmbedder:
    """Embedder for Session 8 semantic search and ingest."""
    return OpenAIEmbedder()


@lru_cache
def get_chunker() -> JSONStructuralChunker:
    """Structural chunker (one chunk per budget component)."""
    return JSONStructuralChunker()


@lru_cache
def get_session_factory() -> async_sessionmaker:
    """Async session factory for database operations."""
    return AsyncSessionLocal


@lru_cache
def get_runtime_config() -> RuntimeModelConfig:
    """Redis-backed runtime overrides for model selection."""
    return RuntimeModelConfig(settings.redis_url)


@lru_cache
def get_runtime_retrieval_config() -> RuntimeRetrievalConfig:
    """Redis-backed runtime overrides for retrieval mode and reranking toggles."""
    return RuntimeRetrievalConfig(settings.redis_url)


@lru_cache
def get_reranker() -> CrossEncoderReranker | None:
    """Optional cross-encoder reranker for recall-then-rerank retrieval."""
    try:
        return CrossEncoderReranker(model_name=settings.rag_pipeline_reranker_model)
    except Exception as exc:
        log.warning("reranker_init_failed", error=str(exc)[:400])
        return None


def get_chunk_store() -> ChunkStore:
    """Data-access layer for pgvector document/chunk storage."""
    return ChunkStore()


def get_rag_ingest_service() -> RagIngestService:
    """Orchestrator: chunk → embed → persist in one transaction."""
    return RagIngestService(
        chunker=get_chunker(),
        embedder=get_embedder(),
        session_factory=get_session_factory(),
        store=get_chunk_store(),
    )


def get_semantic_retriever() -> SemanticRetriever:
    """Semantic search service over the pgvector store."""
    return SemanticRetriever(
        embedder=get_embedder(),
        session_factory=get_session_factory(),
        store=get_chunk_store(),
        reranker=get_reranker(),
    )
