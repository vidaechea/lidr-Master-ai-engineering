import asyncio
import hashlib
import json
import time
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.config import settings
from app.schemas.estimation import EstimationRequest, EstimationResponse
from app.services.estimation_service import EstimationService

log = structlog.get_logger(__name__)

# Redis keys for cache statistics — used by metrics calculations
CACHE_STAT_KEYS = [
    "cache:stats:hits",
    "cache:stats:misses",
    "cache:stats:cost_avoided_usd",
    "cache:stats:latency_hit_ms_sum",
    "cache:stats:latency_hit_count",
    "cache:stats:latency_miss_ms_sum",
    "cache:stats:latency_miss_count",
    "cache:stats:stale_reports",
]


class CachedEstimationService:
    """Decorator that adds Redis exact-match caching to EstimationService.

    Cache key is a SHA-256 hash of all parameters that affect the LLM output,
    ensuring any change in model, temperature, or transcription produces a
    different key.
    """

    def __init__(self, inner: EstimationService) -> None:
        self._inner = inner
        self._redis: aioredis.Redis | None = None
        self._redis_loop: asyncio.AbstractEventLoop | None = None
        self._ttl: int = settings.cache_ttl

    # ------------------------------------------------------------------
    # Redis client — recreated when the running event loop changes
    # (needed for Streamlit which spawns a new loop per request)
    # ------------------------------------------------------------------

    def _get_redis(self) -> aioredis.Redis:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._redis is None or self._redis_loop is not current_loop:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            self._redis_loop = current_loop

        return self._redis

    # ------------------------------------------------------------------
    # Cache key
    # ------------------------------------------------------------------

    def _cache_key(self, request: EstimationRequest, prompt_version: str) -> str:
        payload = json.dumps(
            {
                "transcription": request.transcription,
                "model": request.model or settings.llm_model,
                "temperature": request.temperature,
                "top_p": request.top_p,
                "top_k": request.top_k,
                "reasoning_effort": request.reasoning_effort,
                "max_output_tokens": request.max_output_tokens,
                "example_format": str(request.example_format),
                "num_examples": request.num_examples,
                "prompt_version": prompt_version,
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"llm:{digest}"

    # ------------------------------------------------------------------
    # Metrics helpers
    # ------------------------------------------------------------------

    async def _record_metrics(
        self, *, hit: bool, latency_ms: float, cost_avoided_usd: float = 0.0
    ) -> None:
        try:
            r = self._get_redis()
            async with r.pipeline(transaction=False) as pipe:
                if hit:
                    pipe.incr("cache:stats:hits")
                    pipe.incrbyfloat("cache:stats:cost_avoided_usd", cost_avoided_usd)
                    pipe.incrbyfloat("cache:stats:latency_hit_ms_sum", latency_ms)
                    pipe.incr("cache:stats:latency_hit_count")
                else:
                    pipe.incr("cache:stats:misses")
                    pipe.incrbyfloat("cache:stats:latency_miss_ms_sum", latency_ms)
                    pipe.incr("cache:stats:latency_miss_count")
                await pipe.execute()
        except Exception as exc:
            log.warning("cache_metrics_record_error", error=str(exc))

    @staticmethod
    def _compute_metrics_from_values(values: list) -> dict[str, Any]:
        """Transform raw Redis values into a metric dict (pure function, testable)."""
        hits = int(values[0] or 0)
        misses = int(values[1] or 0)
        total = hits + misses
        cost_avoided = float(values[2] or 0.0)
        lat_hit_sum = float(values[3] or 0.0)
        lat_hit_count = int(values[4] or 0)
        lat_miss_sum = float(values[5] or 0.0)
        lat_miss_count = int(values[6] or 0)
        stale = int(values[7] or 0)

        avg_hit_ms = round(lat_hit_sum / lat_hit_count, 1) if lat_hit_count > 0 else None
        avg_miss_ms = round(lat_miss_sum / lat_miss_count, 1) if lat_miss_count > 0 else None
        speedup = (
            round(avg_miss_ms / avg_hit_ms)
            if avg_hit_ms and avg_miss_ms and avg_hit_ms > 0
            else None
        )

        return {
            "hits": hits,
            "misses": misses,
            "total": total,
            "hit_rate_pct": round(hits / total * 100, 1) if total > 0 else 0.0,
            "cost_avoided_usd": round(cost_avoided, 6),
            "avg_latency_hit_ms": avg_hit_ms,
            "avg_latency_miss_ms": avg_miss_ms,
            "speedup_x": speedup,
            "stale_reports": stale,
            "stale_rate_pct": round(stale / total * 100, 1) if total > 0 else 0.0,
        }

    async def get_metrics(self) -> dict[str, Any]:
        """Return aggregate cache statistics from Redis."""
        try:
            r = self._get_redis()
            values = await r.mget(*CACHE_STAT_KEYS)
        except Exception as exc:
            log.warning("cache_metrics_read_error", error=str(exc))
            return {}

        return self._compute_metrics_from_values(values)

    async def report_stale(self, cache_key: str) -> None:
        """Invalidate a cached entry and increment the stale counter."""
        if not cache_key.startswith("llm:"):
            return
        try:
            r = self._get_redis()
            async with r.pipeline(transaction=False) as pipe:
                pipe.incr("cache:stats:stale_reports")
                pipe.delete(cache_key)
                await pipe.execute()
            log.info("cache_stale_reported", key_prefix=cache_key[:16])
        except Exception as exc:
            log.warning("cache_stale_report_error", error=str(exc))

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def estimate(
        self, request: EstimationRequest, prompt_version: str = "v1"
    ) -> EstimationResponse:
        key = self._cache_key(request, prompt_version)
        t0 = time.perf_counter()

        try:
            cached = await self._get_redis().get(key)
        except Exception as exc:
            log.warning("cache_read_error", error=str(exc))
            cached = None

        if cached:
            raw = json.loads(cached)
            cost_avoided = float(raw.get("turn_cost_usd") or 0.0)
            latency_ms = (time.perf_counter() - t0) * 1000
            log.info("cache_hit", key_prefix=key[:16], model=raw.get("model"), latency_ms=round(latency_ms, 1))
            await self._record_metrics(hit=True, latency_ms=latency_ms, cost_avoided_usd=cost_avoided)
            # Deserialise and mark as cache hit
            response = EstimationResponse.model_validate(raw)
            response = response.model_copy(update={"cache_hit": True, "turn_cost_usd": 0.0})
            return response

        log.info("cache_miss", key_prefix=key[:16])
        response = await self._inner.estimate(request, prompt_version=prompt_version)
        latency_ms = (time.perf_counter() - t0) * 1000

        # Persist the response (without cache metadata)
        try:
            await self._get_redis().setex(key, self._ttl, response.model_dump_json())
        except Exception as exc:
            log.warning("cache_write_error", error=str(exc))

        await self._record_metrics(hit=False, latency_ms=latency_ms)
        return response


# ---------------------------------------------------------------------------
# Kept for backwards-compat with old class name used in Streamlit
# ---------------------------------------------------------------------------
CachedLLMService = CachedEstimationService  # noqa: N816