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
from app.schemas.estimation import UserTier

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
