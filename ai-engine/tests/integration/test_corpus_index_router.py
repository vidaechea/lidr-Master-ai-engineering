from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.dependencies import get_chunk_store, get_corpus_index_service
from app.foundation.persistence.database import get_session
from app.foundation.persistence.repositories.jobs import Job
from app.main import app


class _StubCorpusIndexService:
    async def expand(self, documents, *, document_type, chunk_type, source_prefix="corpus-expansion", on_progress=None):
        _ = (documents, document_type, chunk_type, source_prefix)
        if on_progress is not None:
            on_progress(1)
        return type("Result", (), {"documents_indexed": 1, "documents_skipped": 0, "chunks_created": 2})()


class _StubChunkStore:
    async def corpus_stats(self):
        return [("budget", 3, 9, False)]


class _StubJobsRepository:
    _jobs: dict[uuid.UUID, Job] = {}

    def __init__(self, session):
        _ = session

    def create(self, source_name: str) -> Job:
        job = Job(
            job_id=uuid.uuid4(),
            source_name=source_name,
            status="pending",
            documents_count=0,
            error_message=None,
            started_at=datetime.now(timezone.utc),
            finished_at=None,
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: uuid.UUID) -> Job | None:
        return self._jobs.get(job_id)

    def mark_running(self, job_id: uuid.UUID) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        self._jobs[job_id] = Job(
            job_id=job.job_id,
            source_name=job.source_name,
            status="running",
            documents_count=job.documents_count,
            error_message=job.error_message,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    def set_documents_count(self, job_id: uuid.UUID, documents_count: int) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        self._jobs[job_id] = Job(
            job_id=job.job_id,
            source_name=job.source_name,
            status=job.status,
            documents_count=documents_count,
            error_message=job.error_message,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )

    def mark_completed(self, job_id: uuid.UUID, *, documents_count: int) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        self._jobs[job_id] = Job(
            job_id=job.job_id,
            source_name=job.source_name,
            status="completed",
            documents_count=documents_count,
            error_message=job.error_message,
            started_at=job.started_at,
            finished_at=datetime.now(timezone.utc),
        )

    def mark_failed(self, job_id: uuid.UUID, *, error_message: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        self._jobs[job_id] = Job(
            job_id=job.job_id,
            source_name=job.source_name,
            status="failed",
            documents_count=job.documents_count,
            error_message=error_message,
            started_at=job.started_at,
            finished_at=datetime.now(timezone.utc),
        )


def test_get_corpus_stats(client):
    app.dependency_overrides[get_chunk_store] = lambda: _StubChunkStore()
    try:
        response = client.get("/api/v1/embeddings/index/stats")
    finally:
        app.dependency_overrides.pop(get_chunk_store, None)

    assert response.status_code == 200
    body = response.json()
    assert body["total_chunks"] == 9
    assert body["collections"][0]["collection"] == "budget"


def test_create_index_run_returns_job(client):
    from app.api import corpus_index

    original_repo = corpus_index.JobsRepository
    corpus_index.JobsRepository = _StubJobsRepository
    app.dependency_overrides[get_corpus_index_service] = lambda: _StubCorpusIndexService()
    app.dependency_overrides[get_session] = lambda: None
    try:
        response = client.post(
            "/api/v1/embeddings/index/runs",
            json={
                "documents": [
                    {
                        "budget_id": "B1",
                        "client_metadata": {"name": "Acme", "sector": "saas", "country": "ES"},
                        "project_summary": "Portal project",
                        "main_technology": "python",
                        "year": 2024,
                        "total_estimated_hours": 40,
                        "components": [
                            {
                                "component_id": "DISC-1",
                                "name": "Discovery",
                                "description": "Discovery work",
                                "tech_stack": ["python"],
                                "estimated_hours": 40,
                                "complexity": "medium",
                                "dependencies": [],
                            }
                        ],
                    }
                ]
            },
        )
    finally:
        corpus_index.JobsRepository = original_repo
        app.dependency_overrides.pop(get_corpus_index_service, None)
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 202
    assert response.json()["documents_total"] == 1