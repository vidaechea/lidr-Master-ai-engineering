from __future__ import annotations

import json

from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import Blob
from app.ingestion.parsers.protocol import ParseContext


class BudgetJsonParser:
    supported_formats = {"json"}

    def parse(self, blob: Blob, context: ParseContext) -> list[Document]:
        payload = json.loads(blob.content.decode("utf-8", errors="replace"))
        text = json.dumps(payload, ensure_ascii=True)
        if not text:
            return []
        return [
            Document(
                source_name=context.source.name,
                source_location=str(blob.path),
                source_format="json",
                content=text,
                source_version=context.source_version,
                ingested_at=context.ingested_at,
            )
        ]
