import asyncio
import hashlib
import json
import time
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as aioredis
import structlog
from typing_extensions import Unpack

from app.config import settings
from app.schemas.estimation import ExampleFormat
from app.services.base_llm_service import BaseLLMService, LLMServiceError, _EstimationKwargs

log = structlog.get_logger(__name__)


class CachedLLMService(BaseLLMService):
    """Decorator that adds Redis exact-match caching to any BaseLLMService.

    Cache key is a SHA-256 hash of all parameters that affect the LLM output,
    ensuring any change in model, temperature, or transcription produces a
    different key.
    """

    def __init__(self, inner: BaseLLMService) -> None:
        super().__init__()
        self._inner = inner
        self._redis: aioredis.Redis | None = None
        self._redis_loop: asyncio.AbstractEventLoop | None = None
        self._ttl: int = settings.cache_ttl

    @property
    def _provider_name(self) -> str:
        return self._inner._provider_name

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

    @staticmethod
    def _zero_costs(result: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of result with token counts and costs set to zero.

        A cache hit incurs no LLM cost for the current request.
        """
        r = dict(result)
        r["input_tokens"] = 0
        r["output_tokens"] = 0
        r["reasoning_tokens"] = 0
        r["turn_cost_usd"] = 0.0
        r["total_cost_usd"] = 0.0
        r["pre_call_cost_usd"] = None
        return r

    def _cache_key(self, transcription: str, kwargs: dict[str, Any]) -> str:
        payload = json.dumps(
            {
                "transcription": transcription,
                "model": kwargs.get("model") or settings.llm_model,
                "temperature": kwargs.get("temperature"),
                "top_p": kwargs.get("top_p"),
                "top_k": kwargs.get("top_k"),
                "reasoning_effort": kwargs.get("reasoning_effort", "medium"),
                "max_output_tokens": kwargs.get("max_output_tokens", 2048),
                "example_format": kwargs.get("example_format", ExampleFormat.MARKDOWN),
                "num_examples": kwargs.get("num_examples", 3),
                "pre_call": kwargs.get("pre_call", False),
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

    async def get_metrics(self) -> dict[str, Any]:
        """Return aggregate cache statistics from Redis."""
        try:
            r = self._get_redis()
            values = await r.mget(
                "cache:stats:hits",
                "cache:stats:misses",
                "cache:stats:cost_avoided_usd",
                "cache:stats:latency_hit_ms_sum",
                "cache:stats:latency_hit_count",
                "cache:stats:latency_miss_ms_sum",
                "cache:stats:latency_miss_count",
                "cache:stats:stale_reports",
            )
        except Exception as exc:
            log.warning("cache_metrics_read_error", error=str(exc))
            return {}

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
        self, transcription: str, **kwargs: Unpack[_EstimationKwargs]
    ) -> dict[str, Any]:
        key = self._cache_key(transcription, dict(kwargs))
        t0 = time.perf_counter()

        try:
            cached = await self._get_redis().get(key)
        except Exception as exc:
            log.warning("cache_read_error", error=str(exc))
            cached = None

        if cached:
            raw = json.loads(cached)
            cost_avoided = float(raw.get("turn_cost_usd") or 0.0)
            result: dict[str, Any] = self._zero_costs(raw)
            latency_ms = (time.perf_counter() - t0) * 1000
            result["cache_hit"] = True
            result["cache_key"] = key
            log.info("cache_hit", key_prefix=key[:16], model=result.get("model"), latency_ms=round(latency_ms, 1))
            await self._record_metrics(hit=True, latency_ms=latency_ms, cost_avoided_usd=cost_avoided)
            return result

        log.info("cache_miss", key_prefix=key[:16])
        result = await self._inner.estimate(transcription, **kwargs)
        latency_ms = (time.perf_counter() - t0) * 1000

        # Store clean result — without cache metadata
        try:
            await self._get_redis().setex(key, self._ttl, json.dumps(result))
        except Exception as exc:
            log.warning("cache_write_error", error=str(exc))

        result["cache_hit"] = False
        result["cache_key"] = key
        await self._record_metrics(hit=False, latency_ms=latency_ms)
        return result

    async def estimate_stream(
        self, transcription: str, **kwargs: Unpack[_EstimationKwargs]
    ) -> AsyncIterator[str]:
        key = self._cache_key(transcription, dict(kwargs))
        t0 = time.perf_counter()

        # Cache HIT → yield cached text and skip the LLM call entirely
        try:
            cached = await self._get_redis().get(key)
        except Exception as exc:
            log.warning("cache_read_error", error=str(exc))
            cached = None

        if cached:
            raw = json.loads(cached)
            cost_avoided = float(raw.get("turn_cost_usd") or 0.0)
            data: dict[str, Any] = self._zero_costs(raw)
            latency_ms = (time.perf_counter() - t0) * 1000
            data["cache_hit"] = True
            data["cache_key"] = key
            log.info("cache_hit_stream", key_prefix=key[:16], model=data.get("model"), latency_ms=round(latency_ms, 1))
            yield data["estimation"]
            await self._record_metrics(hit=True, latency_ms=latency_ms, cost_avoided_usd=cost_avoided)
            self._last_stream_result = data
            return

        # Cache MISS → stream from inner, then persist the full result
        log.info("cache_miss_stream", key_prefix=key[:16])
        async for delta in self._inner.estimate_stream(transcription, **kwargs):
            yield delta

        inner_result = self._inner._last_stream_result
        latency_ms = (time.perf_counter() - t0) * 1000
        if inner_result is not None:
            # Store clean result — without cache metadata
            try:
                await self._get_redis().setex(key, self._ttl, json.dumps(inner_result))
            except Exception as exc:
                log.warning("cache_write_error", error=str(exc))
            inner_result["cache_hit"] = False
            inner_result["cache_key"] = key
            await self._record_metrics(hit=False, latency_ms=latency_ms)
        self._last_stream_result = inner_result

    # ------------------------------------------------------------------
    # Abstract method implementations — delegated to inner service
    # ------------------------------------------------------------------

    def _get_model_info(self, model: str | None):  # type: ignore[override]
        return self._inner._get_model_info(model)

    def _count_tokens(self, system_prompt: str, user_message: str, model: str) -> int:
        return self._inner._count_tokens(system_prompt, user_message, model)

    def _build_api_params(self, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        return self._inner._build_api_params(**kwargs)

    async def _call_provider(self, api_params: dict[str, Any]) -> Any:
        return await self._inner._call_provider(api_params)

    async def _call_provider_stream(
        self,
        api_params: dict[str, Any],
        *,
        is_reasoning: bool,
    ) -> AsyncIterator[str]:
        async for chunk in self._inner._call_provider_stream(
            api_params, is_reasoning=is_reasoning
        ):
            yield chunk

    def _parse_provider_response(self, response: Any, *, is_reasoning: bool):  # type: ignore[override]
        return self._inner._parse_provider_response(response, is_reasoning=is_reasoning)
