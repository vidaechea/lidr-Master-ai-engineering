"""Unit tests for app.services.cache_service.CachedLLMService."""
import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.schemas.estimation import ExampleFormat
from app.services.base_llm_service import ModelInfo, ParsedResponse
from app.services.cache_service import CachedLLMService
from app.services.base_llm_service import BaseLLMService


# ---------------------------------------------------------------------------
# Minimal concrete inner service for testing
# ---------------------------------------------------------------------------

class _FakeInnerService(BaseLLMService):
    def __init__(self, result: dict[str, Any]) -> None:
        super().__init__()
        self._result = result
        self.call_count = 0

    def _get_model_info(self, model: str | None) -> tuple[str, ModelInfo]:
        return "fake-model", ModelInfo(
            input_price=1.0,
            output_price=1.0,
            context_window=10_000,
            reasoning=False,
        )

    def _count_tokens(self, system_prompt: str, user_message: str, model: str) -> int:
        return 5

    def _build_api_params(self, **kwargs: Any) -> dict[str, Any]:
        return {}

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        return {}

    async def _call_provider_stream(self, api_params, *, is_reasoning):  # type: ignore[override]
        return
        yield  # make it a generator

    def _parse_provider_response(self, response: Any, *, is_reasoning: bool) -> ParsedResponse:
        return ParsedResponse(
            estimation="",
            response_id="r1",
            input_tokens=0,
            output_tokens=0,
        )

    async def estimate(self, transcription: str, **kwargs) -> dict[str, Any]:  # type: ignore[override]
        self.call_count += 1
        return dict(self._result)

    async def estimate_stream(self, transcription: str, **kwargs):  # type: ignore[override]
        self.call_count += 1
        yield self._result["estimation"]
        self._last_stream_result = dict(self._result)

    @property
    def _provider_name(self) -> str:
        return "fake"


def _make_service(result: dict[str, Any] | None = None) -> CachedLLMService:
    default_result = {
        "estimation": "## Estimation",
        "model": "fake-model",
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": None,
        "turn_cost_usd": 0.001,
        "total_cost_usd": 0.001,
        "response_id": "resp-1",
        "estimated_input_tokens": 95,
        "estimated_precall_cost_usd": 0.0,
        "requirements": None,
        "pre_call_cost_usd": None,
    }
    inner = _FakeInnerService(result or default_result)
    return CachedLLMService(inner=inner)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cache_miss_calls_inner_service():
    """On first call, inner service must be invoked and result stored in Redis."""
    service = _make_service()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # cache miss

    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    result = await service.estimate("long transcription text here")

    assert service._inner.call_count == 1
    assert result["cache_hit"] is False
    mock_redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_cache_hit_skips_inner_service():
    """On cache hit, inner service must NOT be called."""
    service = _make_service()
    stored = {
        "estimation": "cached result",
        "model": "fake-model",
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": None,
        "turn_cost_usd": 0.001,
        "total_cost_usd": 0.001,
        "response_id": "cached-1",
        "estimated_input_tokens": 95,
        "estimated_precall_cost_usd": 0.0,
        "requirements": None,
        "pre_call_cost_usd": None,
    }
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(stored)

    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    result = await service.estimate("long transcription text here")

    assert service._inner.call_count == 0
    assert result["cache_hit"] is True
    assert result["estimation"] == "cached result"
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0
    assert result["turn_cost_usd"] == 0.0
    assert result["total_cost_usd"] == 0.0
    mock_redis.setex.assert_not_awaited()


@pytest.mark.asyncio
async def test_cache_key_is_deterministic():
    """Same inputs must always produce the same cache key."""
    service = _make_service()
    key1 = service._cache_key("same transcription", {"model": "gpt-4o-mini"})
    key2 = service._cache_key("same transcription", {"model": "gpt-4o-mini"})
    assert key1 == key2


@pytest.mark.asyncio
async def test_cache_key_changes_with_model():
    """Different model must produce a different cache key."""
    service = _make_service()
    key1 = service._cache_key("transcription", {"model": "gpt-4o-mini"})
    key2 = service._cache_key("transcription", {"model": "gpt-4-turbo"})
    assert key1 != key2


@pytest.mark.asyncio
async def test_cache_key_changes_with_temperature():
    """Different temperature must produce a different cache key."""
    service = _make_service()
    key1 = service._cache_key("transcription", {"model": "gpt-4o-mini", "temperature": 0.5})
    key2 = service._cache_key("transcription", {"model": "gpt-4o-mini", "temperature": 1.0})
    assert key1 != key2


@pytest.mark.asyncio
async def test_cache_key_changes_with_transcription():
    """Different transcription text must produce a different cache key."""
    service = _make_service()
    key1 = service._cache_key("transcript A content", {})
    key2 = service._cache_key("transcript B content", {})
    assert key1 != key2


@pytest.mark.asyncio
async def test_ttl_is_set_on_write(monkeypatch):
    """Cache writes must use the configured TTL."""
    monkeypatch.setattr(settings, "cache_ttl", 3600)
    service = _make_service()
    service._ttl = settings.cache_ttl

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None

    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    await service.estimate("long transcription text here")

    call_args = mock_redis.setex.await_args
    assert call_args is not None
    _, ttl_arg, _ = call_args.args
    assert ttl_arg == 3600


@pytest.mark.asyncio
async def test_cache_read_error_falls_through_to_inner():
    """If Redis raises on get, the inner service is still called (fail-open)."""
    service = _make_service()
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = ConnectionError("redis down")
    mock_redis.setex.side_effect = ConnectionError("redis down")

    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    result = await service.estimate("long transcription text here")

    assert service._inner.call_count == 1
    assert result["cache_hit"] is False


@pytest.mark.asyncio
async def test_cache_key_has_llm_prefix():
    """Cache keys must start with the 'llm:' namespace prefix."""
    service = _make_service()
    key = service._cache_key("any text", {})
    assert key.startswith("llm:")


@pytest.mark.asyncio
async def test_stream_cache_miss_sets_cache_hit_false():
    """On a stream cache miss, _last_stream_result must have cache_hit=False."""
    service = _make_service()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    # consume the stream
    chunks = []
    async for chunk in service.estimate_stream("some transcription"):
        chunks.append(chunk)

    assert service._last_stream_result is not None
    assert service._last_stream_result["cache_hit"] is False
    mock_redis.setex.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_cache_hit_yields_cached_text_and_skips_inner():
    """On a stream cache hit, cached text is yielded and inner service is NOT called."""
    stored = {
        "estimation": "cached stream result",
        "model": "fake-model",
        "input_tokens": 100,
        "output_tokens": 50,
        "reasoning_tokens": None,
        "turn_cost_usd": 0.001,
        "total_cost_usd": 0.001,
        "response_id": "cached-stream-1",
        "estimated_input_tokens": 95,
        "estimated_precall_cost_usd": 0.0,
        "requirements": None,
        "pre_call_cost_usd": None,
    }
    service = _make_service()
    mock_redis = AsyncMock()
    mock_redis.get.return_value = json.dumps(stored)
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    chunks = []
    async for chunk in service.estimate_stream("some transcription"):
        chunks.append(chunk)

    assert "".join(chunks) == "cached stream result"
    assert service._inner.call_count == 0
    assert service._last_stream_result["cache_hit"] is True
    assert service._last_stream_result["input_tokens"] == 0
    assert service._last_stream_result["output_tokens"] == 0
    assert service._last_stream_result["turn_cost_usd"] == 0.0
    assert service._last_stream_result["total_cost_usd"] == 0.0
    mock_redis.setex.assert_not_awaited()


# ---------------------------------------------------------------------------
# Metrics and stale reporting
# ---------------------------------------------------------------------------

def _mock_redis_with_pipeline(get_return=None) -> AsyncMock:
    """Build a mock Redis with a working async-context-manager pipeline."""
    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)

    mock_redis = AsyncMock()
    mock_redis.get.return_value = get_return
    # pipeline() is called synchronously (not awaited), so use MagicMock
    mock_redis.pipeline = MagicMock(return_value=pipe)
    return mock_redis, pipe


@pytest.mark.asyncio
async def test_record_metrics_increments_hits_on_cache_hit():
    """Cache hit must increment hits counter and cost_avoided via pipeline."""
    service = _make_service()
    mock_redis, pipe = _mock_redis_with_pipeline()
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    await service._record_metrics(hit=True, latency_ms=10.0, cost_avoided_usd=0.005)

    # Pipeline must have been entered and executed
    pipe.incr.assert_any_call("cache:stats:hits")
    pipe.incrbyfloat.assert_any_call("cache:stats:cost_avoided_usd", 0.005)
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_metrics_increments_misses_on_cache_miss():
    """Cache miss must increment misses counter via pipeline."""
    service = _make_service()
    mock_redis, pipe = _mock_redis_with_pipeline()
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    await service._record_metrics(hit=False, latency_ms=500.0)

    pipe.incr.assert_any_call("cache:stats:misses")
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_metrics_returns_correct_hit_rate():
    """get_metrics must compute hit_rate_pct from raw Redis counters."""
    service = _make_service()
    mock_redis = AsyncMock()
    # hits=3, misses=1, cost=0.015, lat_hit_sum=30, lat_hit_count=3,
    # lat_miss_sum=1500, lat_miss_count=1, stale=0
    mock_redis.mget.return_value = ["3", "1", "0.015", "30", "3", "1500", "1", "0"]
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    m = await service.get_metrics()

    assert m["hits"] == 3
    assert m["misses"] == 1
    assert m["total"] == 4
    assert m["hit_rate_pct"] == 75.0
    assert m["cost_avoided_usd"] == pytest.approx(0.015, abs=1e-6)
    assert m["avg_latency_hit_ms"] == 10.0   # 30 / 3
    assert m["avg_latency_miss_ms"] == 1500.0
    assert m["speedup_x"] == 150             # 1500 / 10
    assert m["stale_reports"] == 0
    assert m["stale_rate_pct"] == 0.0


@pytest.mark.asyncio
async def test_get_metrics_empty_redis_returns_zeros():
    """get_metrics must handle all-None counters from an empty Redis."""
    service = _make_service()
    mock_redis = AsyncMock()
    mock_redis.mget.return_value = [None] * 8
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    m = await service.get_metrics()

    assert m["hits"] == 0
    assert m["misses"] == 0
    assert m["hit_rate_pct"] == 0.0
    assert m["avg_latency_hit_ms"] is None
    assert m["avg_latency_miss_ms"] is None
    assert m["speedup_x"] is None


@pytest.mark.asyncio
async def test_report_stale_deletes_key_and_increments_counter():
    """report_stale must delete the cache key and increment stale_reports."""
    service = _make_service()
    mock_redis, pipe = _mock_redis_with_pipeline()
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    key = "llm:abc123deadbeef"
    await service.report_stale(key)

    pipe.incr.assert_any_call("cache:stats:stale_reports")
    pipe.delete.assert_any_call(key)
    pipe.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_report_stale_ignores_non_llm_keys():
    """report_stale must silently do nothing for keys not starting with 'llm:'."""
    service = _make_service()
    mock_redis, pipe = _mock_redis_with_pipeline()
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    await service.report_stale("malicious:key")

    pipe.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_estimate_miss_stores_result_and_records_miss_metric():
    """On a miss, estimate must write to Redis and call _record_metrics with hit=False."""
    service = _make_service()
    mock_redis, pipe = _mock_redis_with_pipeline(get_return=None)
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    result = await service.estimate("some transcription")

    mock_redis.setex.assert_awaited_once()
    assert result["cache_hit"] is False
    assert "cache_key" in result
    # pipeline was used for recording the miss metric
    pipe.incr.assert_any_call("cache:stats:misses")


@pytest.mark.asyncio
async def test_estimate_hit_records_cost_avoided():
    """On a hit, estimate must call _record_metrics with the original cost."""
    stored = {
        "estimation": "cached", "model": "fake-model",
        "input_tokens": 100, "output_tokens": 50, "reasoning_tokens": None,
        "turn_cost_usd": 0.002, "total_cost_usd": 0.002,
        "response_id": "r1", "estimated_input_tokens": 90,
        "estimated_precall_cost_usd": 0.0, "requirements": None,
        "pre_call_cost_usd": None,
    }
    service = _make_service()
    mock_redis, pipe = _mock_redis_with_pipeline(get_return=json.dumps(stored))
    service._redis = mock_redis
    service._redis_loop = asyncio.get_event_loop()

    result = await service.estimate("some transcription")

    assert result["cache_hit"] is True
    assert result["turn_cost_usd"] == 0.0   # zeroed
    # cost_avoided passed to pipeline
    pipe.incrbyfloat.assert_any_call("cache:stats:cost_avoided_usd", 0.002)
