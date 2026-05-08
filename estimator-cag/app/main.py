import structlog
from fastapi import FastAPI

from app.logging import configure_logging
from app.routers import estimations, cache_metrics

configure_logging()

log = structlog.get_logger(__name__)

app = FastAPI(title="Estimator CAG", version="0.1.0")

app.include_router(estimations.router, prefix="/api/v1")
app.include_router(cache_metrics.router, prefix="/api/v1")


@app.get("/health")
def health_check():
    log.debug("health_check called")
    return {"status": "ok"}
