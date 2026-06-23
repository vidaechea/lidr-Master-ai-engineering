from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import structlog

from app.ingestion.catalog.models import CatalogDecision, DataCatalog
from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import FileSystemLoader
from app.ingestion.parsers.protocol import ParseContext
from app.ingestion.parsers.registry import ParserRegistry
from app.foundation.persistence.repositories.jobs import JobsRepository

log = structlog.get_logger(__name__)


class IngestionRejected(Exception):
    pass


def ingest_source(
    *,
    catalog: DataCatalog,
    source_name: str,
    loader: FileSystemLoader,
    registry: ParserRegistry,
    jobs_repo: JobsRepository,
    job_id: uuid.UUID,
) -> list[Document]:
    bound = log.bind(job_id=str(job_id), source_name=source_name)

    source = catalog.find(source_name)
    if source is None:
        raise IngestionRejected(f"source {source_name!r} not found in catalog")
    if source.decision is not CatalogDecision.INCLUDE:
        raise IngestionRejected(
            f"source {source_name!r} has decision={source.decision.value!r}; only 'include' sources can be ingested"
        )

    jobs_repo.mark_running(job_id)
    bound.info("ingestion.started", format=source.format)

    documents: list[Document] = []
    try:
        parser = registry.get(source.format)
        context = ParseContext(
            source=source,
            source_version=catalog.version,
            ingested_at=datetime.now(timezone.utc),
        )
        for blob in loader.iter_blobs(source.location, {source.format}):
            for document in parser.parse(blob, context):
                documents.append(document)

        if source.format == "json":
            documents = _apply_budget_cleaning(documents, bound)
    except Exception as exc:
        bound.error("ingestion.failed", error=str(exc)[:400])
        jobs_repo.mark_failed(job_id, error_message=str(exc))
        raise

    jobs_repo.mark_completed(job_id, documents_count=len(documents))
    bound.info("ingestion.completed", documents_count=len(documents))
    return documents


def _apply_budget_cleaning(documents: list[Document], bound) -> list[Document]:
    if not documents:
        return documents

    cleaning = _load_cleaning_module(bound)
    if cleaning is None:
        return documents

    records, by_budget_id = _extract_budget_records(documents)
    if not records:
        return documents

    clean_budget_records, validate_with_policy = cleaning
    try:
        cleaned = clean_budget_records(records)
        result = validate_with_policy(cleaned)
    except Exception as exc:  # pragma: no cover
        bound.warning("ingestion.cleaning_failed", error=str(exc)[:200])
        return documents

    bound.info("ingestion.cleaning_report", **result.report)
    return _to_valid_documents(result.valid, by_budget_id, documents[0])


def _load_cleaning_module(bound):
    try:
        from app.ingestion.cleaning import clean_budget_records, validate_with_policy
    except Exception as exc:  # pragma: no cover
        bound.warning("ingestion.cleaning_unavailable", error=str(exc)[:200])
        return None
    return clean_budget_records, validate_with_policy


def _extract_budget_records(documents: list[Document]) -> tuple[list[dict], dict[str, Document]]:
    records: list[dict] = []
    by_budget_id: dict[str, Document] = {}
    for doc in documents:
        try:
            payload = json.loads(doc.content)
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue
        records.append(payload)
        budget_id = payload.get("budget_id")
        if isinstance(budget_id, str):
            by_budget_id[budget_id] = doc
    return records, by_budget_id


def _to_valid_documents(valid_frame, by_budget_id: dict[str, Document], fallback: Document) -> list[Document]:
    valid_documents: list[Document] = []
    for _, row in valid_frame.iterrows():
        row_dict = row.to_dict()
        row_dict.pop("content_hash", None)
        budget_id = row_dict.get("budget_id")
        source_doc = by_budget_id.get(budget_id) if isinstance(budget_id, str) else None
        template = source_doc or fallback
        valid_documents.append(
            Document(
                source_name=template.source_name,
                source_location=template.source_location,
                source_format=template.source_format,
                content=json.dumps(row_dict, ensure_ascii=True, default=str),
                source_version=template.source_version,
                ingested_at=template.ingested_at,
            )
        )
    return valid_documents
