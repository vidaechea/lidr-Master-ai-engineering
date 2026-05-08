import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, HTTPException

from app.config import settings

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])

_STAT_KEYS = [
    "cache:stats:hits",
    "cache:stats:misses",
    "cache:stats:cost_avoided_usd",
    "cache:stats:latency_hit_ms_sum",
    "cache:stats:latency_hit_count",
    "cache:stats:latency_miss_ms_sum",
    "cache:stats:latency_miss_count",
    "cache:stats:stale_reports",
]


async def _read_stats() -> dict:
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        values = await r.mget(*_STAT_KEYS)
    finally:
        await r.aclose()

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


@router.get("/metrics")
async def get_cache_metrics():
    if not settings.cache_enabled:
        raise HTTPException(status_code=400, detail="Cache not enabled")
    return await _read_stats()


@router.post("/stale/{key_hash}")
async def report_stale_entry(key_hash: str):
    if not settings.cache_enabled:
        raise HTTPException(status_code=400, detail="Cache not enabled")
    full_key = f"llm:{key_hash}"
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        async with r.pipeline(transaction=False) as pipe:
            pipe.incr("cache:stats:stale_reports")
            pipe.delete(full_key)
            await pipe.execute()
        log.info("cache_stale_reported_api", key_prefix=full_key[:16])
    finally:
        await r.aclose()
    return {"status": "invalidated", "key": full_key}
