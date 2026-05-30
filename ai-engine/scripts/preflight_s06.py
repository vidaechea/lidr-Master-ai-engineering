#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata as importlib_metadata
import sys
import urllib.request
from pathlib import Path
from typing import Callable

OK = "OK"
FAIL = "FAIL"

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class Check:
    def __init__(self, name: str, fn: Callable[[], str | None]) -> None:
        self.name = name
        self._fn = fn

    def run(self) -> bool:
        try:
            detail = self._fn()
        except Exception as exc:  # noqa: BLE001
            print(f"{FAIL}  {self.name}: {type(exc).__name__}: {exc}")
            return False
        if detail:
            print(f"{OK}  {self.name}: {detail}")
        else:
            print(f"{OK}  {self.name}")
        return True


def check_python_version() -> str:
    major, minor, *_ = sys.version_info
    if (major, minor) < (3, 11):
        raise RuntimeError(f"Python 3.11+ required, found {major}.{minor}")
    return f"{major}.{minor}.{sys.version_info.micro}"


def check_catalog() -> str:
    from app.ingestion.catalog import load_catalog

    catalog = load_catalog(ROOT / "data" / "catalog" / "catalog.yaml")
    return f"version {catalog.version}, {len(catalog.included_sources())} included"


def check_seed() -> str:
    seed = ROOT / "data" / "seed"
    budgets = list((seed / "budgets").glob("*.json"))
    transcripts = list((seed / "transcripts").glob("*.txt"))
    xlsx = list(seed.glob("*.xlsx"))
    if not budgets or not transcripts or not xlsx:
        raise RuntimeError(
            f"corpus incomplete: budgets={len(budgets)}, transcripts={len(transcripts)}, xlsx={len(xlsx)}"
        )
    return f"{len(budgets)} json + {len(transcripts)} txt + {len(xlsx)} xlsx"


def check_health_endpoint() -> str:
    with urllib.request.urlopen("http://localhost:8000/health", timeout=2) as r:
        return f"{r.status} OK"


def check_packages() -> str:
    pkgs = ["pandas", "pandera", "sqlalchemy", "pyyaml", "openpyxl", "spacy", "faker"]
    missing = []
    for pkg in pkgs:
        try:
            importlib_metadata.version(pkg)
        except importlib_metadata.PackageNotFoundError:
            missing.append(pkg)
    if missing:
        raise RuntimeError("missing=" + ",".join(missing))
    return f"{len(pkgs)} packages OK"


CHECKS = [
    Check("Python version", check_python_version),
    Check("Required packages", check_packages),
    Check("Catalog validates", check_catalog),
    Check("Corpus seed present", check_seed),
    Check("Estimator /health", check_health_endpoint),
]


def main() -> int:
    failed = 0
    for check in CHECKS:
        if not check.run():
            failed += 1
    if failed:
        print(f"{FAIL}  {failed} check(s) failed")
        return 1
    print(f"{OK}  All checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
