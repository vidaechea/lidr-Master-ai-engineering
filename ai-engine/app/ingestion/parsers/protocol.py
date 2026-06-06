from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.ingestion.catalog.models import CatalogSource
from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import Blob


@dataclass(frozen=True)
class ParseContext:
    source: CatalogSource
    source_version: str
    ingested_at: datetime


class Parser(Protocol):
    supported_formats: set[str]

    def parse(self, blob: Blob, context: ParseContext) -> list[Document]:
        ...
