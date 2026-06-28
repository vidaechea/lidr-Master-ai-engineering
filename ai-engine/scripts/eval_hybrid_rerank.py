#!/usr/bin/env python3
"""Evaluate vector vs hybrid retrieval with and without reranking on a golden set.

Runs four configurations over the same 5 queries and reports:
- Precision@5 (budget-level)
- Mean query latency (ms)
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


@dataclass(frozen=True)
class QueryCase:
    query_id: str
    text: str
    relevant_budget_ids: set[str]


@dataclass(frozen=True)
class EvalConfig:
    name: str
    mode: str
    rerank: bool


CONFIGS = [
    EvalConfig(name="A", mode="vector", rerank=False),
    EvalConfig(name="B", mode="hybrid", rerank=False),
    EvalConfig(name="C", mode="vector", rerank=True),
    EvalConfig(name="D", mode="hybrid", rerank=True),
]


def _load_golden_set(path: Path) -> list[QueryCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    queries = data.get("queries", [])
    if len(queries) != 5:
        raise ValueError("Golden set must contain exactly 5 queries")

    cases: list[QueryCase] = []
    for row in queries:
        cases.append(
            QueryCase(
                query_id=str(row["id"]),
                text=str(row["text"]),
                relevant_budget_ids={str(item) for item in row["relevant_budget_ids"]},
            )
        )
    return cases


def _extract_top_budget_ids(results: list[dict], top_k: int) -> list[str]:
    top_budget_ids: list[str] = []
    seen: set[str] = set()

    for row in results:
        budget_id = str(row.get("metadata", {}).get("budget_id", "")).strip()
        if not budget_id or budget_id in seen:
            continue
        seen.add(budget_id)
        top_budget_ids.append(budget_id)
        if len(top_budget_ids) >= top_k:
            break

    return top_budget_ids


def _precision_at_k(*, predicted_budget_ids: list[str], relevant_budget_ids: set[str], k: int) -> float:
    hits = sum(1 for budget_id in predicted_budget_ids if budget_id in relevant_budget_ids)
    return hits / float(k)


def _run_config(
    *,
    client: httpx.Client,
    endpoint: str,
    headers: dict[str, str],
    cases: list[QueryCase],
    config: EvalConfig,
    k: int,
) -> dict:
    precisions: list[float] = []
    latencies: list[float] = []

    for case in cases:
        response = client.post(
            endpoint,
            json={
                "query": case.text,
                "k": k,
                "mode": config.mode,
                "rerank": config.rerank,
            },
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()

        top_budget_ids = _extract_top_budget_ids(payload.get("results", []), top_k=k)
        precisions.append(
            _precision_at_k(
                predicted_budget_ids=top_budget_ids,
                relevant_budget_ids=case.relevant_budget_ids,
                k=k,
            )
        )
        latencies.append(float(payload.get("search_time_ms", 0.0)))

    mean_precision = sum(precisions) / len(precisions)
    mean_latency = sum(latencies) / len(latencies)

    return {
        "configuration": config.name,
        "search": config.mode,
        "reranking": "Yes" if config.rerank else "No",
        "precision_at_5": round(mean_precision, 4),
        "latency_ms": round(mean_latency, 2),
    }


def _render_markdown_table(rows: list[dict]) -> str:
    header = "| Configuration | Search | Reranking | Precision@5 | Mean Latency (ms) |"
    divider = "|---|---|---|---:|---:|"
    body = [
        (
            f"| {row['configuration']} | {row['search']} | {row['reranking']} | "
            f"{row['precision_at_5']:.4f} | {row['latency_ms']:.2f} |"
        )
        for row in rows
    ]
    return "\n".join([header, divider, *body])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate vector/hybrid retrieval and reranking over a 5-query golden set.")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL for ai-engine API")
    parser.add_argument(
        "--golden-set",
        default="tests/evals/hybrid_rerank_golden_set.json",
        help="Path to golden set JSON (relative to ai-engine root)",
    )
    parser.add_argument("--k", type=int, default=5, help="Evaluation cutoff (default: 5)")
    parser.add_argument("--timeout-seconds", type=float, default=120.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    if args.k != 5:
        raise ValueError("This exercise requires Precision@5, so --k must be 5")

    golden_path = (ROOT / args.golden_set).resolve()
    if not golden_path.exists():
        raise FileNotFoundError(f"Golden set not found: {golden_path}")

    cases = _load_golden_set(golden_path)
    endpoint = f"{args.base_url.rstrip('/')}/api/v1/search"

    headers: dict[str, str] = {}
    if settings.internal_api_key:
        headers["X-Internal-API-Key"] = settings.internal_api_key

    rows: list[dict] = []
    with httpx.Client(timeout=args.timeout_seconds) as client:
        for config in CONFIGS:
            rows.append(
                _run_config(
                    client=client,
                    endpoint=endpoint,
                    headers=headers,
                    cases=cases,
                    config=config,
                    k=args.k,
                )
            )

    print(_render_markdown_table(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
