from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.logging import configure_logging
from app.models.base import Base
from app.routers import auth, estimations, internal, projects, rag_pipeline

configure_logging()
log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    log.info("backend_startup", env=settings.app_env)
    # Create tables on startup only in development — use Alembic in production.
    if settings.app_env == "development":
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    yield
    log.info("backend_shutdown")
    await engine.dispose()


app = FastAPI(
    title="Estimator Backend",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/v1")
app.include_router(projects.router, prefix="/v1")
app.include_router(estimations.router, prefix="/v1")
app.include_router(rag_pipeline.router, prefix="/v1")
app.include_router(internal.router, prefix="/v1")


@app.get("/health")
def health_check():
    return {"status": "ok"}
