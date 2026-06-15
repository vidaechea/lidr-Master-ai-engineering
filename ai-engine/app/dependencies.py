"""FastAPI dependencies for the ai-engine service."""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated

import structlog
from fastapi import Depends, Header
from jose import JWTError, jwt

from app.config import settings
from app.ingestion.catalog import DataCatalog, load_catalog
from app.ingestion.loaders import FileSystemLoader
from app.ingestion.parsers import ParserRegistry, default_registry
from app.domain.schemas.estimation import UserTier
from openai import OpenAI
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.persistence.database import AsyncSessionLocal
from app.generation.rag.chunking.structural import JSONStructuralChunker
from app.generation.rag.embedding.embedder import OpenAIEmbedder
from app.generation.rag.ingest_service import RagIngestService
from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.store.repository import ChunkStore
from app.foundation.llm.runtime_config import RuntimeModelConfig

log = structlog.get_logger(__name__)


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
    )
