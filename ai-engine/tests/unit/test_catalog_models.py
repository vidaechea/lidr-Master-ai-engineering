from __future__ import annotations

from pathlib import Path

from app.ingestion.catalog.loader import load_catalog
from app.ingestion.catalog.models import CatalogDecision


def test_catalog_loader_accepts_rich_schema(tmp_path: Path) -> None:
    catalog_file = tmp_path / "catalog.yaml"
    catalog_file.write_text(
        """
version: "1.0.0"
description: "Catalogo de prueba"
sources:
  - name: presupuestos_json
    description: "Presupuestos firmados"
    location: budgets
    owners: ["comercial@empresa.local"]
    format: json
    volume_estimate: "6 ficheros"
    refresh_declared: "semanal"
    refresh_observed: "carga inicial"
    quality:
      completeness: 4
      consistency: 3
      actuality: 5
      reliability: 4
    sensitivity:
      has_pii: true
      pii_flags: ["PERSON", "EMAIL"]
      access_level: confidential
    lineage: ["crm_export"]
    decision: include
    last_audited: 2026-05-22T09:00:00Z
  - name: rate_card_xlsx
    location: rate_card_2024.xlsx
    format: xlsx
    decision: exclude
    decision_reason: "actuality=1"
""",
        encoding="utf-8",
    )

    catalog = load_catalog(catalog_file)

    assert catalog.version == "1.0.0"
    assert catalog.description == "Catalogo de prueba"
    assert len(catalog.sources) == 2
    assert catalog.find("presupuestos_json") is not None
    assert len(catalog.included_sources()) == 1
    assert catalog.included_sources()[0].decision is CatalogDecision.INCLUDE


def test_catalog_loader_rejects_unknown_extra_field(tmp_path: Path) -> None:
    catalog_file = tmp_path / "catalog.yaml"
    catalog_file.write_text(
        """
version: "1.0.0"
sources:
  - name: source_1
    location: transcripts
    format: txt
    decision: include
    unexpected_field: true
""",
        encoding="utf-8",
    )

    try:
        load_catalog(catalog_file)
        assert False, "Expected catalog validation error"
    except Exception as exc:  # noqa: BLE001
        assert "unexpected_field" in str(exc)
