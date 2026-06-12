"""Async HTTP client that proxies requests to the AI Engine service."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from fastapi import HTTPException
from httpx import AsyncClient, HTTPStatusError, RequestError

from app.config import settings

log = structlog.get_logger(__name__)

_HEADERS: dict[str, str] = {}
if settings.internal_api_key:
    _HEADERS["X-Internal-API-Key"] = settings.internal_api_key

_AI_ENGINE_UNREACHABLE = "AI Engine unreachable"


HttpErrorStrategy = Callable[[HTTPStatusError], tuple[HTTPException, bool, Any]]


def _extract_error_detail(exc: HTTPStatusError) -> Any:
    try:
        payload = exc.response.json()
    except ValueError:
        return exc.response.text

    if isinstance(payload, dict):
        return payload.get("detail", exc.response.text)
    return exc.response.text


def _default_http_error_strategy(exc: HTTPStatusError) -> tuple[HTTPException, bool, Any]:
    status_code = exc.response.status_code
    return (
        HTTPException(status_code=502, detail=f"AI Engine returned {status_code}"),
        True,
        exc.response.text,
    )


def _session_state_http_error_strategy(
    exc: HTTPStatusError,
    *,
    session_id: str,
) -> tuple[HTTPException, bool, Any]:
    status_code = exc.response.status_code
    if status_code == 404:
        return HTTPException(status_code=404, detail=f"Session '{session_id}' not found"), False, None

    return (
        HTTPException(status_code=502, detail=f"AI Engine returned {status_code}"),
        True,
        exc.response.text,
    )


def _session_estimate_http_error_strategy(exc: HTTPStatusError) -> tuple[HTTPException, bool, Any]:
    status_code = exc.response.status_code
    detail = _extract_error_detail(exc)

    if status_code in {400, 401, 404, 413, 422, 429, 500, 503, 504}:
        return HTTPException(status_code=status_code, detail=detail), False, None

    return (
        HTTPException(status_code=502, detail=f"AI Engine returned {status_code}"),
        True,
        detail,
    )


def _cache_metrics_http_error_strategy(exc: HTTPStatusError) -> tuple[HTTPException, bool, Any]:
    status_code = exc.response.status_code
    detail = _extract_error_detail(exc)

    if status_code == 400:
        return HTTPException(status_code=400, detail=detail), False, None

    return (
        HTTPException(status_code=502, detail=f"AI Engine returned {status_code}"),
        True,
        detail,
    )


def _enqueue_http_error_strategy(exc: HTTPStatusError) -> tuple[HTTPException, bool, Any]:
    return HTTPException(status_code=503, detail="Failed to enqueue estimation"), True, str(exc)


async def _request_ai_engine(
    method: str,
    path: str,
    *,
    request_timeout: float,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    form_data: dict[str, str] | None = None,
    files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
    http_error_event: str,
    connection_error_event: str = "ai_engine_connection_error",
    http_error_strategy: HttpErrorStrategy | None = None,
    request_error_status_code: int = 503,
    request_error_detail: str = _AI_ENGINE_UNREACHABLE,
) -> Any:
    strategy = http_error_strategy or _default_http_error_strategy

    async with AsyncClient(
        base_url=settings.ai_engine_url,
        headers=_HEADERS,
        timeout=request_timeout,
    ) as client:
        try:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_body,
                data=form_data,
                files=files,
            )
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as exc:
            http_exception, should_log, log_detail = strategy(exc)
            if should_log:
                log.error(
                    http_error_event,
                    status_code=exc.response.status_code,
                    detail=str(log_detail)[:200],
                )
            raise http_exception from exc
        except RequestError as exc:
            log.error(connection_error_event, error=str(exc))
            raise HTTPException(
                status_code=request_error_status_code,
                detail=request_error_detail,
            ) from exc


async def estimate_sync(request_payload: dict, prompt_version: str) -> dict:
    """Call ``POST /api/v1/estimate`` on the AI Engine and return the JSON response."""
    return await _request_ai_engine(
        "POST",
        "/api/v1/estimate",
        request_timeout=120.0,
        params={"prompt_version": prompt_version},
        json_body=request_payload,
        http_error_event="ai_engine_http_error",
    )


async def estimate_structured(request_payload: dict) -> dict:
    """Call ``POST /api/v1/estimate/structured`` on the AI Engine."""
    return await _request_ai_engine(
        "POST",
        "/api/v1/estimate/structured",
        request_timeout=120.0,
        json_body=request_payload,
        http_error_event="ai_engine_structured_http_error",
    )


async def estimate_acb(request_payload: dict, prompt_version: str) -> dict:
    """Call ``POST /api/v1/estimate/acb`` on the AI Engine and return the JSON response."""
    return await _request_ai_engine(
        "POST",
        "/api/v1/estimate/acb",
        request_timeout=300.0,  # ACB pipeline can take longer: actor + critic + boss × N iterations
        params={"prompt_version": prompt_version},
        json_body=request_payload,
        http_error_event="ai_engine_acb_http_error",
        connection_error_event="ai_engine_acb_connection_error",
    )


async def enqueue_async(request_payload: dict, callback_url: str, prompt_version: str) -> str:
    """Call ``POST /api/v1/internal/estimate/async`` — returns job_id."""
    response_payload = await _request_ai_engine(
        "POST",
        "/api/v1/internal/estimate/async",
        request_timeout=10.0,
        params={"callback_url": callback_url, "prompt_version": prompt_version},
        json_body=request_payload,
        http_error_event="ai_engine_enqueue_error",
        connection_error_event="ai_engine_enqueue_error",
        http_error_strategy=_enqueue_http_error_strategy,
        request_error_status_code=503,
        request_error_detail="Failed to enqueue estimation",
    )
    return response_payload["job_id"]


async def create_session() -> dict[str, Any]:
    """Call ``POST /api/v1/sessions`` on the AI Engine."""
    return await _request_ai_engine(
        "POST",
        "/api/v1/sessions",
        request_timeout=30.0,
        http_error_event="ai_engine_session_create_http_error",
    )


async def get_session_state(session_id: str) -> dict[str, Any]:
    """Call ``GET /api/v1/sessions/{session_id}`` on the AI Engine."""
    return await _request_ai_engine(
        "GET",
        f"/api/v1/sessions/{session_id}",
        request_timeout=30.0,
        http_error_event="ai_engine_session_state_http_error",
        http_error_strategy=lambda exc: _session_state_http_error_strategy(exc, session_id=session_id),
    )


async def estimate_session_multipart(
    session_id: str,
    form_fields: dict[str, str],
    files: list[tuple[str, tuple[str, bytes, str]]],
    prompt_version: str,
) -> dict[str, Any]:
    """Call ``POST /api/v1/sessions/{session_id}/estimate`` with multipart payload."""
    return await _request_ai_engine(
        "POST",
        f"/api/v1/sessions/{session_id}/estimate",
        request_timeout=120.0,
        params={"prompt_version": prompt_version},
        form_data=form_fields,
        files=files,
        http_error_event="ai_engine_session_estimate_http_error",
        http_error_strategy=_session_estimate_http_error_strategy,
    )


async def get_cache_metrics() -> dict[str, Any]:
    """Call ``GET /api/v1/cache/metrics`` on the AI Engine."""
    return await _request_ai_engine(
        "GET",
        "/api/v1/cache/metrics",
        request_timeout=30.0,
        http_error_event="ai_engine_cache_metrics_http_error",
        http_error_strategy=_cache_metrics_http_error_strategy,
    )


async def get_runtime_models() -> dict[str, Any]:
    """Call ``GET /api/v1/config/models`` on the AI Engine."""
    return await _request_ai_engine(
        "GET",
        "/api/v1/config/models",
        request_timeout=30.0,
        http_error_event="ai_engine_runtime_models_http_error",
    )


async def update_runtime_models(changes: dict[str, str | None]) -> dict[str, Any]:
    """Call ``PUT /api/v1/config/models`` on the AI Engine."""
    return await _request_ai_engine(
        "PUT",
        "/api/v1/config/models",
        request_timeout=30.0,
        json_body={"models": changes},
        http_error_event="ai_engine_runtime_models_update_http_error",
    )


async def compare_chunking(request_payload: dict[str, Any]) -> dict[str, Any]:
    """Call ``POST /api/v1/embeddings/compare`` on the AI Engine."""
    return await _request_ai_engine(
        "POST",
        "/api/v1/embeddings/compare",
        request_timeout=600.0,
        json_body=request_payload,
        http_error_event="ai_engine_chunking_compare_http_error",
    )


def _semantic_search_path(use_public_contract: bool | None = None) -> str:
    if use_public_contract is None:
        use_public_contract = settings.ai_engine_public_search_enabled
    return "/api/v1/search" if use_public_contract else "/api/v1/embeddings/search"


async def search_semantic(
    request_payload: dict[str, Any],
    *,
    use_public_contract: bool | None = None,
) -> dict[str, Any]:
    """Call the semantic search contract on the AI Engine."""
    return await _request_ai_engine(
        "POST",
        _semantic_search_path(use_public_contract),
        request_timeout=60.0,
        json_body=request_payload,
        http_error_event="ai_engine_search_http_error",
    )
