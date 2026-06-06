from __future__ import annotations

from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import Blob
from app.ingestion.parsers.protocol import ParseContext


class TranscriptTxtParser:
    supported_formats = {"txt"}

    def parse(self, blob: Blob, context: ParseContext) -> list[Document]:
        text = blob.content.decode("utf-8", errors="replace").strip()
        if not text:
            return []
        return [
            Document(
                source_name=context.source.name,
                source_location=str(blob.path),
                source_format="txt",
                content=text,
                source_version=context.source_version,
                ingested_at=context.ingested_at,
            )
        ]
