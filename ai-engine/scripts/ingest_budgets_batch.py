#!/usr/bin/env python3
"""Batch ingest budget JSON files into /api/v1/embeddings/ingest."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def _build_source_path(file_path: Path) -> str:
    try:
        return file_path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return file_path.as_posix()


def _load_json(file_path: Path) -> dict:
    data = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object")
    return data


def _ingest_one(
    *,
    client: httpx.Client,
    endpoint: str,
    file_path: Path,
    document_type: str,
    headers: dict[str, str],
) -> tuple[str, str]:
    source_path = _build_source_path(file_path)
    content = _load_json(file_path)

    response = client.post(
        endpoint,
        json={
            "source_path": source_path,
            "document_type": document_type,
            "content": content,
        },
        headers=headers,
    )

    if response.status_code == 200:
        payload = response.json()
        return (
            "ingested",
            (
                f"document_id={payload.get('document_id')} "
                f"chunks={payload.get('chunks_created')} "
                f"time_ms={payload.get('ingestion_time_ms')}"
            ),
        )

    if response.status_code == 409:
        payload = response.json()
        return ("duplicate", f"document_id={payload.get('document_id')}")

    return ("error", f"HTTP {response.status_code} -> {response.text}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest all budget JSON files from a folder into ai-engine persistence.",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8001",
        help="Base URL for ai-engine API (default: http://localhost:8001)",
    )
    parser.add_argument(
        "--input-dir",
        default="data/seed/budgets",
        help="Folder containing budget JSON files (default: data/seed/budgets)",
    )
    parser.add_argument(
        "--document-type",
        default="historical_budget",
        help="document_type value sent to ingest endpoint (default: historical_budget)",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=60.0,
        help="HTTP timeout in seconds (default: 60)",
    )
    args = parser.parse_args()

    input_dir = (ROOT / args.input_dir).resolve()
    if not input_dir.exists() or not input_dir.is_dir():
        print(f"ERROR: input directory not found: {input_dir}", file=sys.stderr)
        return 1

    files = sorted(p for p in input_dir.glob("*.json") if p.is_file())
    if not files:
        print(f"ERROR: no JSON files found in {input_dir}", file=sys.stderr)
        return 1

    endpoint = f"{args.base_url.rstrip('/')}/api/v1/embeddings/ingest"
    headers: dict[str, str] = {}
    if settings.internal_api_key:
        headers["X-Internal-API-Key"] = settings.internal_api_key

    print(f"Target endpoint: {endpoint}")
    print(f"Input directory: {input_dir}")
    print(f"Files detected: {len(files)}")

    started = time.perf_counter()
    ingested = 0
    duplicate = 0
    error = 0

    try:
        with httpx.Client(timeout=args.timeout_seconds) as client:
            for idx, file_path in enumerate(files, start=1):
                try:
                    status, detail = _ingest_one(
                        client=client,
                        endpoint=endpoint,
                        file_path=file_path,
                        document_type=args.document_type,
                        headers=headers,
                    )
                except Exception as exc:
                    status, detail = ("error", f"{type(exc).__name__}: {exc}")

                if status == "ingested":
                    ingested += 1
                elif status == "duplicate":
                    duplicate += 1
                else:
                    error += 1

                print(f"[{idx:02d}/{len(files)}] {file_path.name}: {status} ({detail})")
    except httpx.HTTPError as exc:
        print(f"ERROR: request failed: {exc}", file=sys.stderr)
        return 1

    total_ms = int((time.perf_counter() - started) * 1000)
    print("\nSummary")
    print(f"- ingested: {ingested}")
    print(f"- duplicate: {duplicate}")
    print(f"- error: {error}")
    print(f"- elapsed_ms: {total_ms}")

    return 0 if error == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
