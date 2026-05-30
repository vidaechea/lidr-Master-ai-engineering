from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingestion.catalog.models import CatalogDecision, CatalogSource, DataCatalog
from app.ingestion.documents.models import Document
from app.ingestion.orchestrator import IngestionRejected, ingest_source


class _FakeJobsRepo:
    def __init__(self) -> None:
        self.states: list[tuple[str, dict]] = []

    def mark_running(self, job_id: uuid.UUID) -> None:
        self.states.append(("running", {"job_id": str(job_id)}))

    def mark_completed(self, job_id: uuid.UUID, *, documents_count: int) -> None:
        self.states.append(("completed", {"job_id": str(job_id), "documents_count": documents_count}))

    def mark_failed(self, job_id: uuid.UUID, *, error_message: str) -> None:
        self.states.append(("failed", {"job_id": str(job_id), "error_message": error_message}))


class _Blob:
    def __init__(self, content: bytes, path: str = "fake.txt") -> None:
        self.path = Path("fake.txt")
        self.path = Path(path)
        self.content = content


class _FakeLoader:
    def __init__(self, blobs: list[_Blob]) -> None:
        self._blobs = blobs

    def iter_blobs(self, location: str, allowed_formats: set[str]):
        _ = location
        _ = allowed_formats
        for b in self._blobs:
            yield b


class _ParserOk:
    def parse(self, blob, context):
        return [
            Document(
                source_name=context.source.name,
                source_location=str(blob.path),
                source_format=context.source.format,
                content=blob.content.decode("utf-8"),
                source_version=context.source_version,
                ingested_at=context.ingested_at,
            )
        ]


class _ParserJson:
    def parse(self, blob, context):
        return [
            Document(
                source_name=context.source.name,
                source_location=str(blob.path),
                source_format=context.source.format,
                content=blob.content.decode("utf-8"),
                source_version=context.source_version,
                ingested_at=context.ingested_at,
            )
        ]


class _ParserFail:
    def parse(self, blob, context):
        _ = blob
        _ = context
        raise RuntimeError("parse failed")


class _Registry:
    def __init__(self, parser):
        self._parser = parser

    def get(self, fmt: str):
        _ = fmt
        return self._parser


def _catalog(decision: CatalogDecision = CatalogDecision.INCLUDE) -> DataCatalog:
    return DataCatalog(
        version="v1",
        sources=[
            CatalogSource(
                name="sample_transcripts",
                location="transcripts",
                format="txt",
                decision=decision,
                decision_reason="test",
            )
        ],
    )


def _catalog_json(decision: CatalogDecision = CatalogDecision.INCLUDE) -> DataCatalog:
    return DataCatalog(
        version="v1",
        sources=[
            CatalogSource(
                name="sample_budgets",
                location="budgets",
                format="json",
                decision=decision,
                decision_reason="test",
            )
        ],
    )


def test_ingest_source_completes_and_marks_job_completed() -> None:
    jobs = _FakeJobsRepo()
    docs = ingest_source(
        catalog=_catalog(),
        source_name="sample_transcripts",
        loader=_FakeLoader([_Blob(b"hola")]),
        registry=_Registry(_ParserOk()),
        jobs_repo=jobs,
        job_id=uuid.uuid4(),
    )

    assert len(docs) == 1
    assert jobs.states[0][0] == "running"
    assert jobs.states[-1][0] == "completed"
    assert jobs.states[-1][1]["documents_count"] == 1


def test_ingest_source_marks_failed_on_parser_error() -> None:
    jobs = _FakeJobsRepo()

    with pytest.raises(RuntimeError, match="parse failed"):
        ingest_source(
            catalog=_catalog(),
            source_name="sample_transcripts",
            loader=_FakeLoader([_Blob(b"hola")]),
            registry=_Registry(_ParserFail()),
            jobs_repo=jobs,
            job_id=uuid.uuid4(),
        )

    assert jobs.states[0][0] == "running"
    assert jobs.states[-1][0] == "failed"


def test_ingest_source_rejects_unknown_source() -> None:
    jobs = _FakeJobsRepo()

    with pytest.raises(IngestionRejected):
        ingest_source(
            catalog=_catalog(),
            source_name="missing_source",
            loader=_FakeLoader([_Blob(b"hola")]),
            registry=_Registry(_ParserOk()),
            jobs_repo=jobs,
            job_id=uuid.uuid4(),
        )


def test_ingest_source_rejects_non_included_source() -> None:
    jobs = _FakeJobsRepo()

    with pytest.raises(IngestionRejected):
        ingest_source(
            catalog=_catalog(CatalogDecision.REVIEW),
            source_name="sample_transcripts",
            loader=_FakeLoader([_Blob(b"hola")]),
            registry=_Registry(_ParserOk()),
            jobs_repo=jobs,
            job_id=uuid.uuid4(),
        )


def test_ingest_source_json_applies_cleaning_and_keeps_only_valid_rows() -> None:
    pytest.importorskip("pandera")

    jobs = _FakeJobsRepo()
    valid = b'{"budget_id":"BUD-2024-001","year":2024,"total_estimated_hours":480,"project_summary":"Mobile banking API","main_technology":"ruby_on_rails","client_metadata":{"name":"FintechCorp","sector":"finance","country":"ES"},"components":[]}'
    invalid = b'{"budget_id":"BUD-2024-002","year":2024,"total_estimated_hours":-10,"project_summary":"Invalid project","main_technology":"nodejs","client_metadata":{"name":"BadCorp","sector":"tech","country":"US"},"components":[]}'

    docs = ingest_source(
        catalog=_catalog_json(),
        source_name="sample_budgets",
        loader=_FakeLoader([
            _Blob(valid, "valid.json"),
            _Blob(invalid, "invalid.json"),
        ]),
        registry=_Registry(_ParserJson()),
        jobs_repo=jobs,
        job_id=uuid.uuid4(),
    )

    assert len(docs) == 1
    assert "BUD-2024-001" in docs[0].content
    assert jobs.states[-1][0] == "completed"
    assert jobs.states[-1][1]["documents_count"] == 1
