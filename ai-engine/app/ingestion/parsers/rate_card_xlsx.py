from __future__ import annotations

from app.ingestion.documents.models import Document
from app.ingestion.loaders.filesystem import Blob
from app.ingestion.parsers.protocol import ParseContext


class RateCardXlsxParser:
    supported_formats = {"xlsx"}

    def parse(self, blob: Blob, context: ParseContext) -> list[Document]:
        try:
            import pandas as pd
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("pandas/openpyxl required for xlsx parsing") from exc

        sheets = pd.read_excel(blob.path, sheet_name=None)
        rendered_parts: list[str] = []
        for sheet_name, frame in sheets.items():
            rendered_parts.append(f"# sheet: {sheet_name}")
            rendered_parts.append(frame.to_csv(index=False))
        text = "\n".join(rendered_parts).strip()
        if not text:
            return []

        return [
            Document(
                source_name=context.source.name,
                source_location=str(blob.path),
                source_format="xlsx",
                content=text,
                source_version=context.source_version,
                ingested_at=context.ingested_at,
            )
        ]
