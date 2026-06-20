from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.api.internal import enqueue_estimation
from app.domain.schemas.estimation import EstimationRequest


@pytest.mark.anyio
async def test_enqueue_estimation_passes_prompt_version_to_job(monkeypatch):
    enqueue_job = AsyncMock()
    aclose = AsyncMock()

    class PoolStub:
        def __init__(self):
            self.enqueue_job = enqueue_job
            self.aclose = aclose

    create_pool = AsyncMock(return_value=PoolStub())
    monkeypatch.setattr("app.api.internal.arq.create_pool", create_pool)

    request = EstimationRequest(transcription="x" * 30)
    callback_url = "https://backend.test/v1/internal/estimation-callback"

    result = await enqueue_estimation(
        request=request,
        callback_url=callback_url,
        prompt_version="v2",
    )

    assert result["job_id"]
    enqueue_job.assert_awaited_once()
    args = enqueue_job.await_args.args
    kwargs = enqueue_job.await_args.kwargs

    assert args[0] == "estimate_task"
    assert args[1]["transcription"] == request.transcription
    assert args[2] == callback_url
    assert args[4] == "v2"
    assert kwargs["_job_id"] == args[3]
    aclose.assert_awaited_once()

