import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, HTTPException

from app.config import settings
from app.generation.cag.cache_service import CACHE_STAT_KEYS, CachedLLMService

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/cache", tags=["cache"])

async def _read_stats() -> dict:
    """Read and compute cache metrics from Redis.
    
    Delegates metric computation to CachedLLMService to avoid duplication.
    """
    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        values = await r.mget(*CACHE_STAT_KEYS)
    finally:
        await r.aclose()

    return CachedLLMService._compute_metrics_from_values(values)


@router.get("/metrics", responses={400: {"description": "Cache not enabled"}})
async def get_cache_metrics():
    if not settings.cache_enabled:
        raise HTTPException(status_code=400, detail="Cache not enabled")
    return await _read_stats()


@router.post("/stale/{key_hash}", responses={400: {"description": "Cache not enabled"}})
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

