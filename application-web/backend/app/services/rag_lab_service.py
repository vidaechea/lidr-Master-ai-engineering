from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SAMPLE_BUDGETS_PATH = REPO_ROOT / "ai-engine" / "data" / "seed" / "budgets" / "budgets_sample.json"


def load_sample_budgets(path: Path = DEFAULT_SAMPLE_BUDGETS_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Sample budgets corpus must be a JSON array")
    return payload