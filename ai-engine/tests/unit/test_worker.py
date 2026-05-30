from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.worker import estimate_task


class _FakeResponse:
    def model_dump(self) -> dict:
        return {
            "estimation": "ok",
            "model": "gpt-4o-mini",
            "input_tokens": 10,
            "output_tokens": 5,
            "turn_cost_usd": 0.00001,
            "total_cost_usd": 0.00001,
            "estimated_input_tokens": 10,
            "estimated_precall_cost_usd": None,
            "requirements": None,
            "pre_call_cost_usd": None,
            "validation": None,
            "prompt_version": "v2",
        }


class TestEstimateTask:
    async def test_uses_prompt_version_from_job_arguments(self):
        service = type("ServiceStub", (), {"estimate": AsyncMock(return_value=_FakeResponse())})()
        ctx = {"estimation_service": service}
        client_post = AsyncMock()
        async_client_cm = AsyncMock()
        async_client_cm.__aenter__.return_value = type("ClientStub", (), {"post": client_post})()
        async_client_cm.__aexit__.return_value = None

        with patch("app.worker.httpx.AsyncClient", return_value=async_client_cm):
            await estimate_task(
                ctx,
                {"transcription": "x" * 30},
                "https://backend.test/v1/internal/estimation-callback",
                "job-123",
                "v2",
            )

        service.estimate.assert_awaited_once()
        assert service.estimate.await_args.kwargs["prompt_version"] == "v2"
        assert client_post.await_count == 1
        assert client_post.await_args.kwargs["json"]["result"]["prompt_version"] == "v2"
