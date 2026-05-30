from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingestion.catalog.models import CatalogDecision, CatalogSource
from app.ingestion.parsers.protocol import ParseContext
from app.ingestion.parsers.rate_card_xlsx import RateCardXlsxParser


def test_rate_card_xlsx_parser_returns_document(tmp_path: Path) -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")

    file_path = tmp_path / "rate_card.xlsx"
    frame = pd.DataFrame([{"role": "senior_dev", "daily_rate": 500}])
    frame.to_excel(file_path, index=False)

    blob = type("Blob", (), {"path": file_path, "format": "xlsx", "content": file_path.read_bytes()})
    context = ParseContext(
        source=CatalogSource(
            name="rate_card_xlsx",
            location="rate_card_2024.xlsx",
            format="xlsx",
            decision=CatalogDecision.INCLUDE,
            decision_reason="test",
        ),
        source_version="v1",
        ingested_at=datetime.now(timezone.utc),
    )

    parser = RateCardXlsxParser()
    docs = parser.parse(blob, context)

    assert len(docs) == 1
    assert docs[0].source_format == "xlsx"
    assert "sheet:" in docs[0].content
    assert "senior_dev" in docs[0].content
