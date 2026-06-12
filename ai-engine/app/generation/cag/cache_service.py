import asyncio
import hashlib
import json
import time
from typing import Any

import redis.asyncio as aioredis
import structlog

from app.generation.cag.semantic import EstimationSemanticCache
from app.config import MODEL_REGISTRY, settings
from app.domain.schemas.estimation import EstimationRequest, EstimationResponse, UserTier
from app.foundation.prompts.prompt_builder import PromptBuilder
from app.generation.conversation.sessions import ConversationHistory, ProjectMetadata
from app.domain.estimation_service import EstimationService

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
    """Decorator that adds two Redis cache layers to EstimationService.

    Layer 1 — exact match: SHA-256 hash of all request parameters.
    Layer 2 — semantic similarity: vector search via redisvl (Redis Stack).
    Any change in model, temperature, or transcription bypasses layer 1 and
    falls through to the semantic similarity check before hitting the LLM.
    """

    def __init__(
        self,
        inner: EstimationService,
        *,
        semantic_cache: EstimationSemanticCache | None = None,
    ) -> None:
        self._inner = inner
        self._redis: aioredis.Redis | None = None
        self._redis_loop: asyncio.AbstractEventLoop | None = None
        self._ttl: int = settings.cache_ttl
        self._semantic: EstimationSemanticCache | None = (
            semantic_cache if semantic_cache is not None else self._build_semantic_cache()
        )

    # ------------------------------------------------------------------
    # Semantic cache factory — only built when settings enable it
    # ------------------------------------------------------------------

    @staticmethod
    def _build_semantic_cache() -> EstimationSemanticCache | None:
        if not settings.semantic_cache_enabled:
            return None
        try:
            import redis as sync_redis
            from redisvl.utils.vectorize import OpenAITextVectorizer

            client = sync_redis.from_url(settings.redis_url)
            vectorizer = OpenAITextVectorizer(
                model="text-embedding-3-small",
                api_config={"api_key": settings.openai_api_key},
            )
            log.info("semantic_cache_initialized")
            return EstimationSemanticCache(
                redis_client=client,
                vectorizer=vectorizer,
                threshold=settings.semantic_cache_threshold,
                ttl=settings.cache_ttl,
                log_only=settings.semantic_cache_log_only,
            )
        except Exception as exc:
            log.warning("semantic_cache_init_failed", error=str(exc))
            return None

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

    def _cache_key_multi_turn(
        self,
        request: EstimationRequest,
        history: ConversationHistory,
        prompt_version: str,
        project_metadata: ProjectMetadata | None,
    ) -> str:
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
                "output_format": str(request.output_format),
                "pre_call": request.pre_call,
                "prompt_version": prompt_version,
                "history": history.as_dicts(),
                "project_metadata": (
                    project_metadata.model_dump(mode="json")
                    if project_metadata is not None
                    else None
                ),
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"llm:multi:{digest}"

    def _cache_key_multi_turn_turn_exact(
        self,
        request: EstimationRequest,
        prompt_version: str,
    ) -> str:
        """Exact key for the current user turn, independent of prior history.

        This keeps session cache useful when the same transcript is submitted
        again in the same conversation and history has already grown.
        """
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
                "output_format": str(request.output_format),
                "pre_call": request.pre_call,
                "prompt_version": prompt_version,
            },
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()
        return f"llm:multi:turn:{digest}"

    @staticmethod
    def _append_history_for_cached_multi_turn(
        request: EstimationRequest,
        response: EstimationResponse,
        history: ConversationHistory,
        prompt_version: str,
        project_metadata: ProjectMetadata | None,
    ) -> None:
        """Mirror history mutation done by EstimationService.estimate_multi_turn()."""
        model_name = request.model or settings.llm_model
        model_cfg = MODEL_REGISTRY[model_name]
        builder = PromptBuilder(
            request,
            model_cfg,
            prompt_version,
            project_metadata=project_metadata,
        )
        history.add("user", builder.user_prompt)
        history.add("assistant", response.estimation)

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
        self, request: EstimationRequest, prompt_version: str = "v1",
        tier: UserTier | None = None,
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
            await self._record_metrics(hit=True, latency_ms=latency_ms, cost_avoided_usd=cost_avoided)
            # Deserialise and mark as cache hit
            response = EstimationResponse.model_validate(raw)
            response = response.model_copy(update={"cache_hit": True, "turn_cost_usd": 0.0})
            return response

        log.info("cache_miss", key_prefix=key[:16])

        # -------------------------------------------------------------------
        # Layer 2: semantic similarity cache
        # -------------------------------------------------------------------
        if self._semantic is not None:
            try:
                sem_result = await asyncio.to_thread(
                    self._semantic.lookup, request, prompt_version
                )
            except Exception as exc:
                log.warning("semantic_cache_lookup_error", error=str(exc))
                sem_result = None

            if sem_result is not None:
                cost_avoided = float(sem_result.turn_cost_usd or 0.0)
                latency_ms = (time.perf_counter() - t0) * 1000
                await self._record_metrics(
                    hit=True, latency_ms=latency_ms, cost_avoided_usd=cost_avoided
                )
                return sem_result.model_copy(update={"turn_cost_usd": 0.0})

        # -------------------------------------------------------------------
        # Layer 3: LLM call
        # -------------------------------------------------------------------
        response = await self._inner.estimate(request, prompt_version=prompt_version, tier=tier)
        latency_ms = (time.perf_counter() - t0) * 1000

        # Persist in exact cache
        try:
            await self._get_redis().setex(key, self._ttl, response.model_dump_json())
        except Exception as exc:
            log.warning("cache_write_error", error=str(exc))

        # Persist in semantic cache
        if self._semantic is not None:
            try:
                await asyncio.to_thread(
                    self._semantic.store, request, response, prompt_version
                )
            except Exception as exc:
                log.warning("semantic_cache_store_error", error=str(exc))

        await self._record_metrics(hit=False, latency_ms=latency_ms)
        return response

    async def estimate_multi_turn(
        self,
        request: EstimationRequest,
        history: ConversationHistory,
        prompt_version: str = "v1",
        project_metadata: ProjectMetadata | None = None,
        session_id: str | None = None,
        enriched_transcript_chars: int | None = None,
        attachments_total_chars: int = 0,
        messages_in_window: int | None = None,
        anchors_count: int = 0,
        summary_chars: int = 0,
        cache_hit_kind: str = "none",
        last_resolved_tier: str | None = None,
    ) -> EstimationResponse:
        """Cache-aware wrapper for multi-turn estimations used by session routes.

        Semantic cache is intentionally skipped for multi-turn because history and
        evolving metadata strongly affect the response.

        Accepts optional context parameters for observation event emission.
        """
        from app.domain.schemas.observation import CacheHitKind

        key = self._cache_key_multi_turn(request, history, prompt_version, project_metadata)
        turn_key = self._cache_key_multi_turn_turn_exact(request, prompt_version)
        t0 = time.perf_counter()

        try:
            cached = await self._get_redis().get(key)
        except Exception as exc:
            log.warning("cache_read_error", error=str(exc))
            cached = None

        if cached is None:
            try:
                cached = await self._get_redis().get(turn_key)
            except Exception as exc:
                log.warning("cache_read_error", error=str(exc))
                cached = None

        if cached:
            raw = json.loads(cached)
            cost_avoided = float(raw.get("turn_cost_usd") or 0.0)
            latency_ms = (time.perf_counter() - t0) * 1000
            await self._record_metrics(
                hit=True,
                latency_ms=latency_ms,
                cost_avoided_usd=cost_avoided,
            )
            response = EstimationResponse.model_validate(raw)
            response = response.model_copy(update={"cache_hit": True, "turn_cost_usd": 0.0})
            self._append_history_for_cached_multi_turn(
                request,
                response,
                history,
                prompt_version,
                project_metadata,
            )
            # Update cache_hit_kind to reflect exact match
            cache_hit_kind = "exact"
            return response

        log.info("cache_miss_multi_turn", key_prefix=key[:16])

        response = await self._inner.estimate_multi_turn(
            request,
            history=history,
            prompt_version=prompt_version,
            project_metadata=project_metadata,
            session_id=session_id,
            enriched_transcript_chars=enriched_transcript_chars,
            attachments_total_chars=attachments_total_chars,
            messages_in_window=messages_in_window,
            anchors_count=anchors_count,
            summary_chars=summary_chars,
            cache_hit_kind=CacheHitKind(cache_hit_kind) if cache_hit_kind in ["none", "exact", "semantic"] else CacheHitKind.NONE,
            last_resolved_tier=last_resolved_tier,
        )
        latency_ms = (time.perf_counter() - t0) * 1000

        try:
            await self._get_redis().setex(key, self._ttl, response.model_dump_json())
            await self._get_redis().setex(turn_key, self._ttl, response.model_dump_json())
        except Exception as exc:
            log.warning("cache_write_error", error=str(exc))

        await self._record_metrics(hit=False, latency_ms=latency_ms)
        return response


# ---------------------------------------------------------------------------
# Kept for backwards-compat with old class name used in Streamlit
# ---------------------------------------------------------------------------
CachedLLMService = CachedEstimationService  # noqa: N816

