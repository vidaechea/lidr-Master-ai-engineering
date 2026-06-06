"""pytest configuration for backend tests.

Uses an in-memory SQLite database (via aiosqlite) for unit and integration
tests so no running PostgreSQL is required.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import sqlite as _sqlite_dialect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.main import app
from app.models.base import Base
from app.dependencies import get_db

# --- SQLite compatibility shims for PostgreSQL-specific column types ----------
# JSONB has no renderer in SQLite's type compiler; map it to JSON for tests.
_sqlite_dialect.base.SQLiteTypeCompiler.visit_JSONB = (  # type: ignore[attr-defined]
    _sqlite_dialect.base.SQLiteTypeCompiler.visit_JSON
)
# ------------------------------------------------------------------------------

_TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
async def engine():
    _engine = create_async_engine(
        _TEST_DB_URL,
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    await _engine.dispose()


@pytest.fixture
async def db(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(db):
    app.dependency_overrides[get_db] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
async def registered_user(client):
    """Register a unique user and return credentials + tokens."""
    email = f"test_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    response = await client.post(
        "/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201
    data = response.json()
    return {"email": email, "password": password, **data}


@pytest.fixture
async def auth_headers(registered_user):
    """Return Authorization header dict for a freshly registered user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}
