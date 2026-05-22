import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings
from app.logging import configure_logging
from app.routers import estimations, cache_metrics, internal, sessions

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


app = FastAPI(title="Estimator CAG — AI Engine", version="0.1.0")
app.add_middleware(InternalKeyMiddleware)

app.include_router(estimations.router, prefix="/api/v1")
app.include_router(cache_metrics.router, prefix="/api/v1")
app.include_router(internal.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    log.debug("health_check called")
    return {"status": "ok"}
