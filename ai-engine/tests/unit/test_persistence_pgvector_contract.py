from __future__ import annotations

import runpy
import tomllib
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import yaml


AI_ENGINE_ROOT = Path.cwd().resolve()
PROJECT_ROOT = AI_ENGINE_ROOT.parent


def _resolve_compose_path() -> Path:
    candidates = [
        PROJECT_ROOT / "docker-compose.yml",
        Path("/workspaces/lidr-Master-ai-engineering/docker-compose.yml"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    pytest.skip("docker-compose.yml not available in this test environment")


def test_pyproject_includes_persistence_dependencies() -> None:
    pyproject_path = AI_ENGINE_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    dependencies: list[str] = data["project"]["dependencies"]

    assert any(dep.startswith("sqlalchemy>=2.0") for dep in dependencies)
    assert any(dep.startswith("asyncpg>=0.29") for dep in dependencies)
    assert any(dep.startswith("pgvector>=0.3") for dep in dependencies)
    assert any(dep.startswith("alembic>=1.13") for dep in dependencies)


def test_compose_config_has_pgvector_and_ai_engine_db_dependency() -> None:
    compose_path = _resolve_compose_path()
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    postgres = compose["services"]["postgres"]
    assert postgres["image"] == "pgvector/pgvector:pg16"
    assert postgres["healthcheck"]["test"] == [
        "CMD-SHELL",
        "pg_isready -U ${POSTGRES_USER:-estimator} -d ${POSTGRES_DB:-estimator}",
    ]

    ai_engine = compose["services"]["ai-engine"]
    assert ai_engine["environment"]["DATABASE_URL"].startswith("postgresql+asyncpg://")
    assert ai_engine["depends_on"]["postgres"]["condition"] == "service_healthy"


@pytest.mark.parametrize(
    "expected_snippet",
    [
        'import os',
        "import pgvector.sqlalchemy",
        'database_url = os.getenv("DATABASE_URL")',
        'config.set_main_option("sqlalchemy.url", database_url)',
        'connection.dialect.ischema_names["vector"] = pgvector.sqlalchemy.Vector',
    ],
)
def test_alembic_env_has_database_url_and_vector_registration(expected_snippet: str) -> None:
    env_path = AI_ENGINE_ROOT / "alembic" / "env.py"
    content = env_path.read_text(encoding="utf-8")

    assert expected_snippet in content


def _load_migration_module() -> dict[str, object]:
    migration_path = AI_ENGINE_ROOT / "alembic" / "versions" / "0001_initial_schema.py"
    return runpy.run_path(str(migration_path))


class _FakeOp:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def execute(self, sql: str) -> None:
        self.calls.append(("execute", sql))

    def create_table(self, name: str, *columns: object, **kwargs: object) -> None:
        self.calls.append(("create_table", name, columns, kwargs))

    def create_index(self, name: str, table_name: str, columns: list[str], **kwargs: object) -> None:
        self.calls.append(("create_index", name, table_name, columns, kwargs))

    def drop_index(self, name: str, table_name: str | None = None) -> None:
        self.calls.append(("drop_index", name, table_name))

    def drop_table(self, name: str) -> None:
        self.calls.append(("drop_table", name))


def test_migration_upgrade_contract() -> None:
    migration = _load_migration_module()
    fake_op = _FakeOp()

    upgrade = cast(Callable[[], None], migration["upgrade"])
    upgrade.__globals__["op"] = fake_op
    upgrade()

    assert migration["revision"] == "0001"
    assert migration["down_revision"] is None

    assert ("execute", "CREATE EXTENSION IF NOT EXISTS vector") in fake_op.calls

    created_tables = [call for call in fake_op.calls if call[0] == "create_table"]
    assert {call[1] for call in created_tables} == {"documents", "chunks"}

    index_names = {call[1] for call in fake_op.calls if call[0] == "create_index"}
    assert index_names == {
        "ix_documents_source_path",
        "ix_chunks_document_id",
        "ix_chunks_chunk_type",
        "ix_chunks_metadata_gin",
    }


def test_migration_downgrade_contract() -> None:
    migration = _load_migration_module()
    fake_op = _FakeOp()

    downgrade = cast(Callable[[], None], migration["downgrade"])
    downgrade.__globals__["op"] = fake_op
    downgrade()

    drop_indexes = [call for call in fake_op.calls if call[0] == "drop_index"]
    assert [call[1] for call in drop_indexes] == [
        "ix_chunks_metadata_gin",
        "ix_chunks_chunk_type",
        "ix_chunks_document_id",
        "ix_documents_source_path",
    ]

    dropped_tables = [call for call in fake_op.calls if call[0] == "drop_table"]
    assert [call[1] for call in dropped_tables] == ["chunks", "documents"]
