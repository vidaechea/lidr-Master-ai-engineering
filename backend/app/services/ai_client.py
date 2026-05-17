from __future__ import annotations

"""Async HTTP client that proxies requests to the AI Engine service."""

from typing import Any

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


async def create_session() -> dict[str, Any]:
    """Call ``POST /api/v1/sessions`` on the AI Engine."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=30.0,
    ) as client:
        try:
            response = await client.post("/api/v1/sessions")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            log.error(
                "ai_engine_session_create_http_error",
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


async def get_session_state(session_id: str) -> dict[str, Any]:
    """Call ``GET /api/v1/sessions/{session_id}`` on the AI Engine."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=30.0,
    ) as client:
        try:
            response = await client.get(f"/api/v1/sessions/{session_id}")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found") from exc
            log.error(
                "ai_engine_session_state_http_error",
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


async def estimate_session_multipart(
    session_id: str,
    form_fields: dict[str, str],
    files: list[tuple[str, tuple[str, bytes, str]]],
    prompt_version: str,
) -> dict[str, Any]:
    """Call ``POST /api/v1/sessions/{session_id}/estimate`` with multipart payload."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=120.0,
    ) as client:
        try:
            response = await client.post(
                f"/api/v1/sessions/{session_id}/estimate",
                params={"prompt_version": prompt_version},
                data=form_fields,
                files=files,
            )
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            status_code = exc.response.status_code
            detail: Any
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = exc.response.text

            if status_code in {400, 401, 404, 413, 422, 429, 500, 503, 504}:
                raise HTTPException(status_code=status_code, detail=detail) from exc

            log.error(
                "ai_engine_session_estimate_http_error",
                status_code=status_code,
                detail=str(detail)[:200],
            )
            raise HTTPException(status_code=502, detail=f"AI Engine returned {status_code}") from exc
        except RequestError as exc:
            log.error("ai_engine_connection_error", error=str(exc))
            raise HTTPException(status_code=503, detail="AI Engine unreachable") from exc


async def get_cache_metrics() -> dict[str, Any]:
    """Call ``GET /api/v1/cache/metrics`` on the AI Engine."""
    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=30.0,
    ) as client:
        try:
            response = await client.get("/api/v1/cache/metrics")
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            status_code = exc.response.status_code
            detail: Any
            try:
                detail = exc.response.json().get("detail")
            except Exception:
                detail = exc.response.text

            if status_code == 400:
                raise HTTPException(status_code=400, detail=detail) from exc

            log.error(
                "ai_engine_cache_metrics_http_error",
                status_code=status_code,
                detail=str(detail)[:200],
            )
            raise HTTPException(status_code=502, detail=f"AI Engine returned {status_code}") from exc
        except RequestError as exc:
            log.error("ai_engine_connection_error", error=str(exc))
            raise HTTPException(status_code=503, detail="AI Engine unreachable") from exc
