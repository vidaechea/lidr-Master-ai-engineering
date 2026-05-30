from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from fastapi import HTTPException
from httpx import Request, RequestError, Response

from app.services import ai_client


def _patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    response_factory: Callable[[str, str], Response] | None = None,
    error_factory: Callable[[str, str], Exception] | None = None,
) -> None:
    class _StubAsyncClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self) -> _StubAsyncClient:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

        async def request(
            self,
            method: str,
            path: str,
            *,
            params: dict[str, str] | None = None,
            json: dict[str, Any] | None = None,
            data: dict[str, str] | None = None,
            files: list[tuple[str, tuple[str, bytes, str]]] | None = None,
        ) -> Response:
            await asyncio.sleep(0)
            _ = (params, json, data, files)
            if error_factory is not None:
                raise error_factory(method, path)
            assert response_factory is not None
            return response_factory(method, path)

    monkeypatch.setattr(ai_client, "AsyncClient", _StubAsyncClient)


def _json_response(method: str, path: str, status_code: int, payload: dict[str, Any]) -> Response:
    request = Request(method, f"http://testserver{path}")
    return Response(status_code=status_code, json=payload, request=request)


def _text_response(method: str, path: str, status_code: int, text: str) -> Response:
    request = Request(method, f"http://testserver{path}")
    return Response(status_code=status_code, text=text, request=request)


class TestAiClientErrorMapping:
    async def test_get_session_state_maps_404_to_domain_not_found(self, monkeypatch: pytest.MonkeyPatch):
        _patch_async_client(
            monkeypatch,
            response_factory=lambda method, path: _text_response(method, path, 404, "missing"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await ai_client.get_session_state("sid-404")

        assert exc_info.value.status_code == 404
        assert exc_info.value.detail == "Session 'sid-404' not found"

    async def test_estimate_session_multipart_passthroughs_422_detail(self, monkeypatch: pytest.MonkeyPatch):
        _patch_async_client(
            monkeypatch,
            response_factory=lambda method, path: _json_response(
                method,
                path,
                422,
                {"detail": "validation failed"},
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await ai_client.estimate_session_multipart(
                session_id="sid-1",
                form_fields={"transcript": "valid transcript with enough length"},
                files=[],
                prompt_version="v1",
            )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail == "validation failed"

    async def test_get_cache_metrics_passthroughs_400_detail(self, monkeypatch: pytest.MonkeyPatch):
        _patch_async_client(
            monkeypatch,
            response_factory=lambda method, path: _json_response(
                method,
                path,
                400,
                {"detail": "invalid query parameter"},
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await ai_client.get_cache_metrics()

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "invalid query parameter"

    async def test_estimate_sync_maps_request_error_to_503_unreachable(self, monkeypatch: pytest.MonkeyPatch):
        _patch_async_client(
            monkeypatch,
            error_factory=lambda method, path: RequestError(
                "network down",
                request=Request(method, f"http://testserver{path}"),
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await ai_client.estimate_sync(
                request_payload={"transcription": "sample"},
                prompt_version="v1",
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "AI Engine unreachable"

    async def test_enqueue_async_maps_request_error_to_failed_enqueue(self, monkeypatch: pytest.MonkeyPatch):
        _patch_async_client(
            monkeypatch,
            error_factory=lambda method, path: RequestError(
                "timeout",
                request=Request(method, f"http://testserver{path}"),
            ),
        )

        with pytest.raises(HTTPException) as exc_info:
            await ai_client.enqueue_async(
                request_payload={"transcription": "sample"},
                callback_url="http://callback",
                prompt_version="v1",
            )

        assert exc_info.value.status_code == 503
        assert exc_info.value.detail == "Failed to enqueue estimation"

    async def test_estimate_sync_maps_http_status_to_502(self, monkeypatch: pytest.MonkeyPatch):
        _patch_async_client(
            monkeypatch,
            response_factory=lambda method, path: _text_response(method, path, 500, "boom"),
        )

        with pytest.raises(HTTPException) as exc_info:
            await ai_client.estimate_sync(
                request_payload={"transcription": "sample"},
                prompt_version="v1",
            )

        assert exc_info.value.status_code == 502
        assert exc_info.value.detail == "AI Engine returned 500"