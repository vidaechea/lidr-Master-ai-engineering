from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


@lru_cache
def create_engine_from_settings() -> Engine:
    return create_engine(
        settings.database_url,
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


def get_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
