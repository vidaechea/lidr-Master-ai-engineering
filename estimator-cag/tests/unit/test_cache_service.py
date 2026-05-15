"""Unit tests for CachedEstimationService — two-layer cache.

Layers under test:
  1. Exact match  — Redis GET by SHA-256 key.
  2. Semantic     — redisvl vector search (EstimationSemanticCache).
  3. LLM fallthrough — inner.estimate() called when both caches miss,
                       result stored in both layers.

No real Redis, redisvl, or LLM calls are made.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.estimation import EstimationRequest, EstimationResponse
from app.services.cache_service import CachedEstimationService

VALID_TX = "Build a multi-tenant SaaS analytics platform with reporting and user authentication."


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _req(**kwargs) -> EstimationRequest:
    defaults: dict = dict(transcription=VALID_TX)
    defaults.update(kwargs)
    return EstimationRequest(**defaults)


def _resp(**kwargs) -> EstimationResponse:
    defaults: dict = dict(
        estimation="## Plan",
        model="gpt-4o-mini",
        response_id="r-001",
        input_tokens=400,
        output_tokens=150,
        turn_cost_usd=0.08,
        total_cost_usd=0.08,
        estimated_input_tokens=400,
        estimated_precall_cost_usd=None,
        requirements=None,
        pre_call_cost_usd=None,
        validation=None,
        prompt_version="v1",
    )
    defaults.update(kwargs)
    return EstimationResponse(**defaults)


def _make_redis_mock(*, cached: str | None = None) -> AsyncMock:
    """Return an async Redis mock. If ``cached`` is set, GET returns it (exact hit)."""
    r = AsyncMock()
    r.get.return_value = cached
    pipe = AsyncMock()
    pipe.__aenter__ = AsyncMock(return_value=pipe)
    pipe.__aexit__ = AsyncMock(return_value=False)
    r.pipeline.return_value = pipe
    return r


async def _passthrough_to_thread(fn, *args, **kwargs):
    """Drop-in for asyncio.to_thread that calls fn synchronously (no thread pool)."""
    return fn(*args, **kwargs)


# ---------------------------------------------------------------------------
# Pure function: _compute_metrics_from_values
# ---------------------------------------------------------------------------


class TestComputeMetricsFromValues:
    def test_all_zeros_returns_zero_hit_rate_and_no_averages(self):
        result = CachedEstimationService._compute_metrics_from_values([0] * 8)

        assert result["hit_rate_pct"] == 0.0
        assert result["avg_latency_hit_ms"] is None
        assert result["avg_latency_miss_ms"] is None
        assert result["speedup_x"] is None

    def test_hit_rate_computed_correctly(self):
        # hits=3, misses=1 → 75 %
        values = [3, 1, 0.15, 300.0, 3, 500.0, 1, 0]
        result = CachedEstimationService._compute_metrics_from_values(values)

        assert result["hit_rate_pct"] == 75.0
        assert result["hits"] == 3
        assert result["misses"] == 1
        assert result["total"] == 4

    def test_speedup_x_computed_from_average_latencies(self):
        # avg_hit=50ms, avg_miss=500ms → speedup=10×
        values = [1, 1, 0.05, 50.0, 1, 500.0, 1, 0]
        result = CachedEstimationService._compute_metrics_from_values(values)

        assert result["speedup_x"] == 10


# ---------------------------------------------------------------------------
# Cache-key determinism
# ---------------------------------------------------------------------------


class TestCacheKey:
    @pytest.fixture
    def svc(self):
        return CachedEstimationService(MagicMock(), semantic_cache=None)

    def test_same_request_produces_same_key(self, svc):
        req = _req()
        assert svc._cache_key(req, "v1") == svc._cache_key(req, "v1")

    def test_different_transcription_produces_different_key(self, svc):
        req_a = _req(transcription="Build a mobile payment app with QR scanning for merchants.")
        req_b = _req(transcription="Build a fraud detection pipeline for real-time banking alerts.")
        assert svc._cache_key(req_a, "v1") != svc._cache_key(req_b, "v1")


# ---------------------------------------------------------------------------
# Layer 1: exact cache hit
# ---------------------------------------------------------------------------


class TestEstimateExactCacheHit:
    async def test_returns_cached_response_without_calling_inner(self):
        inner = MagicMock()
        inner.estimate = AsyncMock()
        resp = _resp()
        svc = CachedEstimationService(inner, semantic_cache=None)
        redis_mock = _make_redis_mock(cached=resp.model_dump_json())

        with (
            patch.object(svc, "_get_redis", return_value=redis_mock),
            patch.object(svc, "_record_metrics", AsyncMock()),
        ):
            result = await svc.estimate(_req())

        inner.estimate.assert_not_called()
        assert result.model == resp.model

    async def test_exact_hit_zeroes_turn_cost_usd(self):
        inner = MagicMock()
        inner.estimate = AsyncMock()
        resp = _resp(turn_cost_usd=0.08)
        svc = CachedEstimationService(inner, semantic_cache=None)
        redis_mock = _make_redis_mock(cached=resp.model_dump_json())

        with (
            patch.object(svc, "_get_redis", return_value=redis_mock),
            patch.object(svc, "_record_metrics", AsyncMock()),
        ):
            result = await svc.estimate(_req())

        assert result.turn_cost_usd == 0.0


# ---------------------------------------------------------------------------
# Layer 2: semantic cache hit
# ---------------------------------------------------------------------------


class TestEstimateSemanticCacheHit:
    @pytest.fixture
    def sem_cache(self):
        m = MagicMock()
        m.lookup.return_value = None  # default: miss; individual tests override
        return m

    async def test_semantic_hit_does_not_call_inner(self, sem_cache):
        inner = MagicMock()
        inner.estimate = AsyncMock()
        resp = _resp(turn_cost_usd=0.05)
        sem_cache.lookup.return_value = resp
        svc = CachedEstimationService(inner, semantic_cache=sem_cache)

        with (
            patch.object(svc, "_get_redis", return_value=_make_redis_mock()),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            result = await svc.estimate(_req())

        inner.estimate.assert_not_called()
        assert result.model == resp.model

    async def test_semantic_hit_zeroes_turn_cost_usd(self, sem_cache):
        inner = MagicMock()
        inner.estimate = AsyncMock()
        sem_cache.lookup.return_value = _resp(turn_cost_usd=0.05)
        svc = CachedEstimationService(inner, semantic_cache=sem_cache)

        with (
            patch.object(svc, "_get_redis", return_value=_make_redis_mock()),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            result = await svc.estimate(_req())

        assert result.turn_cost_usd == 0.0

    async def test_semantic_lookup_error_falls_through_to_llm(self, sem_cache):
        llm_resp = _resp()
        inner = MagicMock()
        inner.estimate = AsyncMock(return_value=llm_resp)
        sem_cache.lookup.side_effect = RuntimeError("Redis Stack unavailable")
        svc = CachedEstimationService(inner, semantic_cache=sem_cache)

        with (
            patch.object(svc, "_get_redis", return_value=_make_redis_mock()),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            result = await svc.estimate(_req())

        inner.estimate.assert_called_once()
        assert result.model == llm_resp.model


# ---------------------------------------------------------------------------
# Layer 3: LLM fallthrough and dual storage
# ---------------------------------------------------------------------------


class TestEstimateLLMFallthrough:
    """Both caches miss → inner.estimate is called and both caches are populated."""

    @pytest.fixture
    def sem_cache(self):
        m = MagicMock()
        m.lookup.return_value = None
        return m

    @pytest.fixture
    def llm_resp(self):
        return _resp()

    @pytest.fixture
    def inner(self, llm_resp):
        m = MagicMock()
        m.estimate = AsyncMock(return_value=llm_resp)
        return m

    @pytest.fixture
    def svc(self, inner, sem_cache):
        return CachedEstimationService(inner, semantic_cache=sem_cache)

    async def test_calls_inner_estimate_on_double_miss(self, svc, inner):
        with (
            patch.object(svc, "_get_redis", return_value=_make_redis_mock()),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            await svc.estimate(_req())

        inner.estimate.assert_called_once()

    async def test_llm_response_stored_in_exact_cache(self, svc):
        redis_mock = _make_redis_mock()

        with (
            patch.object(svc, "_get_redis", return_value=redis_mock),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            await svc.estimate(_req())

        redis_mock.setex.assert_called_once()

    async def test_llm_response_stored_in_semantic_cache(self, svc, sem_cache):
        with (
            patch.object(svc, "_get_redis", return_value=_make_redis_mock()),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            await svc.estimate(_req())

        sem_cache.store.assert_called_once()

    async def test_semantic_store_error_is_swallowed(self, svc, sem_cache, llm_resp):
        sem_cache.store.side_effect = RuntimeError("Redis write failed")

        with (
            patch.object(svc, "_get_redis", return_value=_make_redis_mock()),
            patch.object(svc, "_record_metrics", AsyncMock()),
            patch("asyncio.to_thread", side_effect=_passthrough_to_thread),
        ):
            result = await svc.estimate(_req())

        # Call completes successfully despite the store failure
        assert result.model == llm_resp.model


# ---------------------------------------------------------------------------
# _build_semantic_cache() — settings-driven factory
# ---------------------------------------------------------------------------


class TestBuildSemanticCache:
    def test_returns_none_when_semantic_cache_disabled(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "semantic_cache_enabled", False)
        assert CachedEstimationService._build_semantic_cache() is None

    def test_returns_none_and_does_not_raise_when_redisvl_missing(self, monkeypatch):
        """redisvl is not installed in this environment; the factory must fail
        safely and return None instead of propagating ImportError."""
        from app.config import settings

        monkeypatch.setattr(settings, "semantic_cache_enabled", True)
        monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")

        result = CachedEstimationService._build_semantic_cache()

        assert result is None
