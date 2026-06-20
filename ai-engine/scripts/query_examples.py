#!/usr/bin/env python3
"""Run five representative semantic-search queries against /search endpoint."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

QUERY_CASES: list[tuple[str, str]] = [
    (
        "Componente directo conocido",
        "REST API development with JWT authentication for financial sector",
    ),
    (
        "Reformulacion semantica",
        "secure backend service with token-based access control for banking applications",
    ),
    (
        "Dominio distinto",
        "mobile application for restaurant reservations",
    ),
    (
        "Consulta ambigua",
        "integration with external system",
    ),
    (
        "Consulta muy especifica",
        "migration from monolith to microservices architecture using Kubernetes",
    ),
]


def _truncate(text: str, max_len: int = 120) -> str:
    single_line = " ".join(text.split())
    if len(single_line) <= max_len:
        return single_line
    return f"{single_line[: max_len - 3]}..."


def _print_results(title: str, query: str, payload: dict) -> None:
    print(f"\n=== {title} ===")
    print(f"Query: {query}")
    print(f"k={payload.get('k')}  search_time_ms={payload.get('search_time_ms')}")

    results = payload.get("results", [])
    if not results:
        print("(sin resultados)")
        return

    for idx, row in enumerate(results, start=1):
        print(
            f"{idx:>2}. chunk_id={row['chunk_id']}  distance={row['distance']:.4f}  "
            f"chunk_type={row['chunk_type']}"
        )
        print(f"    {_truncate(row['content'])}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run representative semantic search queries against /api/v1/embeddings/search",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Base URL for ai-engine API (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--k",
        type=int,
        default=5,
        help="Top-k results per query (default: 5)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="HTTP timeout in seconds (default: 30)",
    )
    args = parser.parse_args()

    if args.k < 1:
        print("ERROR: --k must be >= 1", file=sys.stderr)
        return 1

    endpoint = f"{args.base_url.rstrip('/')}/api/v1/embeddings/search"
    headers: dict[str, str] = {}
    if settings.internal_api_key:
        headers["X-Internal-API-Key"] = settings.internal_api_key

    print(f"Target endpoint: {endpoint}")
    started = time.perf_counter()

    try:
        with httpx.Client(timeout=args.timeout_seconds) as client:
            for title, query in QUERY_CASES:
                response = client.post(
                    endpoint,
                    json={"query": query, "k": args.k},
                    headers=headers,
                )

                if response.status_code != 200:
                    print(f"\n=== {title} ===")
                    print(f"Query: {query}")
                    print(f"ERROR: HTTP {response.status_code} -> {response.text}")
                    continue

                _print_results(title=title, query=query, payload=response.json())
    except httpx.HTTPError as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    print(f"\nDone. Total elapsed: {elapsed_ms} ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
