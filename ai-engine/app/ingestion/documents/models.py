from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Document:
    source_name: str
    source_location: str
    source_format: str
    content: str
    source_version: str
    ingested_at: datetime
