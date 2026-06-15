import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.dependencies import get_runtime_config
from app.foundation.llm.litellm_service import create_litellm_router_service
from app.logging import configure_logging
from app.api import cache_metrics, config, estimations, ingestion, internal, sessions
from app.api.embeddings import ingest_router
from app.api import search

configure_logging()

log = structlog.get_logger(__name__)

_UNPROTECTED_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


class InternalKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests to /api/* that lack the correct X-Internal-API-Key header.

    Only active when ``settings.internal_api_key`` is non-empty, so local
    development works without any configuration.
    """

    async def dispatch(self, request: Request, call_next):
        secret = settings.internal_api_key
        if secret and request.url.path not in _UNPROTECTED_PATHS:
            provided = request.headers.get("X-Internal-API-Key")
            if provided != secret:
                log.warning(
                    "internal_key_rejected",
                    path=request.url.path,
                    client=request.client.host if request.client else "unknown",
                )
                return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
        return await call_next(request)


API_PREFIX = "/api/v1"

app = FastAPI(title="Estimator CAG — AI Engine", version="0.1.0")
app.add_middleware(InternalKeyMiddleware)

app.include_router(estimations.router, prefix=API_PREFIX)
app.include_router(cache_metrics.router, prefix=API_PREFIX)
app.include_router(internal.router, prefix=API_PREFIX)
app.include_router(sessions.router, prefix=API_PREFIX)
app.include_router(ingestion.router, prefix=API_PREFIX)
app.include_router(ingest_router, prefix=API_PREFIX + "/embeddings")
app.include_router(config.router, prefix=API_PREFIX)
app.include_router(search.router, prefix=API_PREFIX)


@app.on_event("startup")
async def bootstrap_runtime_models() -> None:
    """Align the in-memory LiteLLM router with persisted runtime overrides.

    Runtime overrides live in Redis and survive process restarts. We reload them
    at startup so the router does not fall back to .env defaults after reboot.
    """
    runtime_config = get_runtime_config()
    snapshot = await runtime_config.snapshot()
    primary_model = snapshot["LLM_MODEL"].effective
    fallback_model = snapshot["LLM_FALLBACK"].effective

    create_litellm_router_service(
        primary_model=primary_model,
        fallback_model=fallback_model,
    )
    log.info(
        "runtime_models_bootstrapped",
        primary_model=primary_model,
        fallback_model=fallback_model,
    )


@app.get("/health")
def health_check():
    log.debug("health_check called")
    return {"status": "ok"}

