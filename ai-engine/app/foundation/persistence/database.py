from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _to_sync_database_url(database_url: str) -> str:
    # ai-engine uses a synchronous SQLAlchemy engine in this module.
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    return database_url


def _to_async_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql+psycopg://"):
        return database_url.replace("postgresql+psycopg://", "postgresql+asyncpg://", 1)
    return database_url


@lru_cache
def create_engine_from_settings() -> Engine:
    return create_engine(
        _to_sync_database_url(settings.database_url),
        pool_pre_ping=True,
        future=True,
    )


@lru_cache
def create_async_engine_from_settings() -> AsyncEngine:
    return create_async_engine(
        _to_async_database_url(settings.database_url),
        pool_pre_ping=True,
        future=True,
    )


SessionLocal = sessionmaker(
    bind=create_engine_from_settings(),
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=create_async_engine_from_settings(),
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


async def get_async_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
