from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class Blob:
    path: Path
    format: str
    content: bytes


class FileSystemLoader:
    def __init__(self, data_root: Path) -> None:
        self._data_root = data_root

    def iter_blobs(self, location: str, allowed_formats: set[str]) -> Iterable[Blob]:
        base = (self._data_root / location).resolve()
        if base.is_file():
            fmt = base.suffix.removeprefix(".").lower()
            if fmt in allowed_formats:
                yield Blob(path=base, format=fmt, content=base.read_bytes())
            return

        if not base.exists():
            raise FileNotFoundError(f"ingestion location not found: {base}")

        for file_path in base.rglob("*"):
            if not file_path.is_file():
                continue
            fmt = file_path.suffix.removeprefix(".").lower()
            if fmt not in allowed_formats:
                continue
            yield Blob(path=file_path, format=fmt, content=file_path.read_bytes())
