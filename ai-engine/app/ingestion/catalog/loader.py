from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.ingestion.catalog.models import DataCatalog


def load_catalog(path: Path) -> DataCatalog:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return DataCatalog.model_validate(data)
