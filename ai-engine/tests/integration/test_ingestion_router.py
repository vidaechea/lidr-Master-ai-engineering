from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Force sqlite for test import-time engine creation before importing app modules.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from app.config import settings

settings.database_url = "sqlite+pysqlite:///:memory:"

from app.dependencies import get_catalog, get_filesystem_loader, get_parser_registry
from app.ingestion.catalog.models import CatalogDecision, CatalogSource, DataCatalog
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.parsers.registry import default_registry

from app.main import app
from app.foundation.persistence.database import get_session
from app.foundation.persistence.models import IngestionJobRow


def _client_with_overrides(tmp_path: Path) -> TestClient:
    engine = create_engine(
        "sqlite+pysqlite://",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    IngestionJobRow.__table__.create(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    def _get_session_override():
        session = local()
        try:
            yield session
        finally:
            session.close()

    data_root = tmp_path / "seed"
    transcripts = data_root / "transcripts"
    transcripts.mkdir(parents=True, exist_ok=True)
    (transcripts / "sample.txt").write_text("texto de prueba", encoding="utf-8")

    catalog = DataCatalog(
        version="v-test",
        sources=[
            CatalogSource(
                name="sample_transcripts",
                location="transcripts",
                format="txt",
                decision=CatalogDecision.INCLUDE,
                decision_reason="test",
            ),
            CatalogSource(
                name="review_source",
                location="transcripts",
                format="txt",
                decision=CatalogDecision.REVIEW,
                decision_reason="manual",
            ),
        ],
    )

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_catalog] = lambda: catalog
    app.dependency_overrides[get_filesystem_loader] = lambda: FileSystemLoader(data_root=data_root)
    app.dependency_overrides[get_parser_registry] = default_registry

    client = TestClient(app)
    return client


def test_create_ingestion_run_returns_202_and_job_id() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = _client_with_overrides(Path(temp_dir))
        response = client.post("/api/v1/ingestion/runs", json={"source_name": "sample_transcripts"})

        assert response.status_code == 202
        body = response.json()
        assert "job_id" in body
        assert body["source_name"] == "sample_transcripts"
        assert body["status"] in {"pending", "running", "completed"}


def test_create_ingestion_run_unknown_source_returns_404() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = _client_with_overrides(Path(temp_dir))
        response = client.post("/api/v1/ingestion/runs", json={"source_name": "missing"})

        assert response.status_code == 404
        assert response.json()["detail"]["reason"] == "unknown_source"


def test_create_ingestion_run_review_source_returns_400() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = _client_with_overrides(Path(temp_dir))
        response = client.post("/api/v1/ingestion/runs", json={"source_name": "review_source"})

        assert response.status_code == 400
        assert response.json()["detail"]["reason"] == "source_not_included"


def test_get_ingestion_job_returns_404_for_missing_job() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        client = _client_with_overrides(Path(temp_dir))
        response = client.get("/api/v1/ingestion/jobs/00000000-0000-0000-0000-000000000001")

        assert response.status_code == 404
