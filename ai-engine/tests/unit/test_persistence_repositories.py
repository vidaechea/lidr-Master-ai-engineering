from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Base
from app.persistence.repositories.jobs import JobsRepository
from app.persistence.repositories.mappings import MappingsRepository


def _session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    local = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return local()


def test_jobs_repository_create_and_get() -> None:
    session = _session()
    repo = JobsRepository(session)

    created = repo.create("sample_transcripts")
    fetched = repo.get(created.job_id)

    assert fetched is not None
    assert fetched.source_name == "sample_transcripts"
    assert fetched.status == "pending"
    assert fetched.documents_count == 0


def test_jobs_repository_status_transitions() -> None:
    session = _session()
    repo = JobsRepository(session)

    created = repo.create("sample_transcripts")
    repo.mark_running(created.job_id)
    running = repo.get(created.job_id)
    assert running is not None and running.status == "running"

    repo.mark_completed(created.job_id, documents_count=7)
    completed = repo.get(created.job_id)
    assert completed is not None
    assert completed.status == "completed"
    assert completed.documents_count == 7
    assert completed.finished_at is not None


def test_jobs_repository_mark_failed_sets_error_message() -> None:
    session = _session()
    repo = JobsRepository(session)

    created = repo.create("sample_budgets")
    repo.mark_failed(created.job_id, error_message="boom")

    failed = repo.get(created.job_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error_message == "boom"
    assert failed.finished_at is not None


def test_mappings_repository_lookup_or_create_is_idempotent() -> None:
    session = _session()
    repo = MappingsRepository(session)

    mapping_1 = repo.lookup_or_create("PERSON", "hash-1", lambda: "Ana Perez")
    mapping_2 = repo.lookup_or_create("PERSON", "hash-1", lambda: "Otro Nombre")

    assert mapping_1.original_hash == "hash-1"
    assert mapping_1.pseudonym == "Ana Perez"
    assert mapping_2.pseudonym == "Ana Perez"


def test_mappings_repository_forget_existing_mapping() -> None:
    session = _session()
    repo = MappingsRepository(session)

    repo.lookup_or_create("EMAIL_ADDRESS", "hash-email", lambda: "x@y.com")
    deleted = repo.forget("EMAIL_ADDRESS", "hash-email")

    assert deleted is True
    assert repo.lookup("EMAIL_ADDRESS", "hash-email") is None


def test_jobs_repository_get_unknown_returns_none() -> None:
    session = _session()
    repo = JobsRepository(session)

    missing = repo.get(uuid.uuid4())
    assert missing is None
