from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _resolve_sample_budgets_path() -> Path:
    env_path = os.getenv("RAG_BUDGETS_PATH")
    if env_path:
        return Path(env_path)

    # Bundled corpus inside the backend package — always present in Docker.
    bundled = Path(__file__).resolve().parent.parent / "data" / "budgets_sample.json"
    if bundled.exists():
        return bundled

    # Monorepo dev fallback: traverse parents looking for the ai-engine seed.
    current = Path(__file__).resolve()
    for parent in [current, *current.parents]:
        candidate = parent / "ai-engine" / "data" / "seed" / "budgets" / "budgets_sample.json"
        if candidate.exists():
            return candidate

    return bundled


DEFAULT_SAMPLE_BUDGETS_PATH = _resolve_sample_budgets_path()


def load_sample_budgets(path: Path = DEFAULT_SAMPLE_BUDGETS_PATH) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, list):
        raise ValueError("Sample budgets corpus must be a JSON array")
    return payload