"""Unit tests for EstimationSemanticCache.

All redisvl imports are stubbed via sys.modules so the tests run without
the optional Redis Stack / redisvl dependency.

Coverage:
  - bucket_for(): None-safe field handling for project_type and detail_level.
  - lookup(): empty index, below-threshold miss, above-threshold hit, log_only mode.
  - store(): happy path and exception swallowing.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

from app.schemas.estimation import (
    DetailLevel,
    EstimationRequest,
    EstimationResponse,
    OutputFormat,
    ProjectType,
)

VALID_TX = "Build a multi-tenant SaaS analytics platform with user authentication and reporting."


# ---------------------------------------------------------------------------
# sys.modules stub — runs before every test in this module
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _stub_redisvl(monkeypatch):
    """Replace redisvl sub-modules so the deferred imports inside
    EstimationSemanticCache methods never raise ModuleNotFoundError."""
    for key in ("redisvl", "redisvl.index", "redisvl.query", "redisvl.query.filter"):
        monkeypatch.setitem(sys.modules, key, MagicMock())


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
        input_tokens=300,
        output_tokens=100,
        turn_cost_usd=0.05,
        total_cost_usd=0.05,
        estimated_input_tokens=300,
        estimated_precall_cost_usd=None,
        requirements=None,
        pre_call_cost_usd=None,
        validation=None,
        prompt_version="v1",
    )
    defaults.update(kwargs)
    return EstimationResponse(**defaults)


def _hit_record(distance: float, result_json: str) -> dict:
    """Mimic a redisvl query result record."""
    return {"vector_distance": str(distance), "result_json": result_json}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def index_mock() -> MagicMock:
    return MagicMock()


@pytest.fixture
def vectorizer_mock() -> MagicMock:
    v = MagicMock()
    v.embed.return_value = [0.1] * 1536
    return v


@pytest.fixture
def cache(index_mock, vectorizer_mock):
    from app.cache.semantic import EstimationSemanticCache

    c = EstimationSemanticCache(
        redis_client=MagicMock(),
        vectorizer=vectorizer_mock,
        threshold=0.90,
        ttl=3600,
        log_only=False,
    )
    c.index = index_mock  # replace the redisvl-created index with a controlled mock
    return c


@pytest.fixture
def log_only_cache(index_mock, vectorizer_mock):
    from app.cache.semantic import EstimationSemanticCache

    c = EstimationSemanticCache(
        redis_client=MagicMock(),
        vectorizer=vectorizer_mock,
        threshold=0.90,
        ttl=3600,
        log_only=True,
    )
    c.index = index_mock
    return c


# ---------------------------------------------------------------------------
# bucket_for()
# ---------------------------------------------------------------------------


class TestBucketFor:
    def test_all_optional_fields_set_uses_their_values(self):
        from app.cache.semantic import EstimationSemanticCache

        req = _req(
            project_type=ProjectType.WEB_SAAS,
            detail_level=DetailLevel.DETAILED,
            output_format=OutputFormat.LINE_ITEMS,
        )
        assert EstimationSemanticCache.bucket_for(req, "v2") == "v2:web_saas:detailed:line_items"

    def test_project_type_none_defaults_to_any(self):
        from app.cache.semantic import EstimationSemanticCache

        req = _req(project_type=None, detail_level=DetailLevel.SUMMARY)
        bucket = EstimationSemanticCache.bucket_for(req, "v1")
        assert bucket == "v1:any:summary:phases_table"

    def test_detail_level_none_defaults_to_any(self):
        from app.cache.semantic import EstimationSemanticCache

        req = _req(project_type=ProjectType.MOBILE_APP, detail_level=None)
        bucket = EstimationSemanticCache.bucket_for(req, "v1")
        assert bucket == "v1:mobile_app:any:phases_table"

    def test_both_optional_none_produces_any_any(self):
        from app.cache.semantic import EstimationSemanticCache

        req = _req(project_type=None, detail_level=None)
        assert EstimationSemanticCache.bucket_for(req, "v1") == "v1:any:any:phases_table"


# ---------------------------------------------------------------------------
# lookup()
# ---------------------------------------------------------------------------


class TestLookup:
    def test_empty_index_returns_none(self, cache, index_mock):
        index_mock.query.return_value = []
        assert cache.lookup(_req(), "v1") is None

    def test_below_threshold_returns_none(self, cache, index_mock):
        # distance=0.20 → similarity=0.80, threshold=0.90 → miss
        index_mock.query.return_value = [_hit_record(0.20, _resp().model_dump_json())]
        assert cache.lookup(_req(), "v1") is None

    def test_above_threshold_returns_estimation_response(self, cache, index_mock):
        # distance=0.04 → similarity=0.96, threshold=0.90 → hit
        resp = _resp(model="gpt-4o-mini")
        index_mock.query.return_value = [_hit_record(0.04, resp.model_dump_json())]

        result = cache.lookup(_req(), "v1")

        assert isinstance(result, EstimationResponse)
        assert result.model == resp.model
        assert result.estimation == resp.estimation

    def test_log_only_returns_none_even_above_threshold(self, log_only_cache, index_mock):
        # similarity=0.98 > 0.90, but log_only=True → never return a hit
        resp = _resp()
        index_mock.query.return_value = [_hit_record(0.02, resp.model_dump_json())]
        assert log_only_cache.lookup(_req(), "v1") is None

    def test_lookup_uses_transcription_for_embedding(self, cache, index_mock, vectorizer_mock):
        index_mock.query.return_value = []
        cache.lookup(_req(), "v1")
        vectorizer_mock.embed.assert_called_once_with(VALID_TX)


# ---------------------------------------------------------------------------
# store()
# ---------------------------------------------------------------------------


class TestStore:
    def test_calls_index_load_with_correct_bucket(self, cache, index_mock, vectorizer_mock):
        resp = _resp()
        cache.store(_req(project_type=None, detail_level=None), resp, "v1")

        index_mock.load.assert_called_once()
        payload = index_mock.load.call_args[0][0]
        assert payload[0]["bucket"] == "v1:any:any:phases_table"

    def test_calls_index_load_with_transcription_embedding(
        self, cache, index_mock, vectorizer_mock
    ):
        cache.store(_req(), _resp(), "v1")
        vectorizer_mock.embed.assert_called_with(VALID_TX)

    def test_store_exception_is_swallowed(self, cache, index_mock):
        index_mock.load.side_effect = RuntimeError("Redis Stack unavailable")
        # Must not raise — store failures are non-fatal
        cache.store(_req(), _resp(), "v1")
