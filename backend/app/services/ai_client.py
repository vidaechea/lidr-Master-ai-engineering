from __future__ import annotations

"""Async HTTP client that proxies requests to the AI Engine service."""

import structlog
from fastapi import HTTPException
from httpx import AsyncClient, HTTPStatusError, RequestError

from app.config import settings

log = structlog.get_logger(__name__)

_HEADERS: dict[str, str] = {}
if settings.internal_api_key:
    _HEADERS["X-Internal-API-Key"] = settings.internal_api_key


async def estimate_sync(request_payload: dict) -> dict:
    """Call ``POST /api/v1/estimate`` on the AI Engine and return the JSON response."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=120.0,
    ) as client:
        try:
            response = await client.post("/api/v1/estimate", json=request_payload)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            log.error(
                "ai_engine_http_error",
                status_code=exc.response.status_code,
                detail=exc.response.text[:200],
            )
            raise HTTPException(
                status_code=502,
                detail=f"AI Engine returned {exc.response.status_code}",
            ) from exc
        except RequestError as exc:
            log.error("ai_engine_connection_error", error=str(exc))
            raise HTTPException(status_code=503, detail="AI Engine unreachable") from exc


async def estimate_structured(request_payload: dict) -> dict:
    """Call ``POST /api/v1/estimate/structured`` on the AI Engine."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=120.0,
    ) as client:
        try:
            response = await client.post("/api/v1/estimate/structured", json=request_payload)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            log.error(
                "ai_engine_structured_http_error",
                status_code=exc.response.status_code,
            )
            raise HTTPException(
                status_code=502,
                detail=f"AI Engine returned {exc.response.status_code}",
            ) from exc
        except RequestError as exc:
            log.error("ai_engine_connection_error", error=str(exc))
            raise HTTPException(status_code=503, detail="AI Engine unreachable") from exc


async def enqueue_async(request_payload: dict, callback_url: str) -> str:
    """Call ``POST /api/v1/internal/estimate/async`` — returns job_id."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=10.0,
    ) as client:
        try:
            response = await client.post(
                "/api/v1/internal/estimate/async",
                json=request_payload,
                params={"callback_url": callback_url},
            )
            response.raise_for_status()
            return response.json()["job_id"]
        except (HTTPStatusError, RequestError) as exc:
            log.error("ai_engine_enqueue_error", error=str(exc))
            raise HTTPException(status_code=503, detail="Failed to enqueue estimation") from exc
