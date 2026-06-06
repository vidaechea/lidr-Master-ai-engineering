#!/usr/bin/env python3
"""Benchmark embedding latency and vector shape across providers.

Usage:
    python scripts/benchmark_embeddings.py
    python scripts/benchmark_embeddings.py --model text-embedding-3-large --dimensions 1024
    python scripts/benchmark_embeddings.py --skip-local
"""
from __future__ import annotations

import argparse
import time
import sys
from pathlib import Path
from typing import Callable

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

DEFAULT_TEXTS = [
    "OAuth 2.0 authentication backend with JWT tokens for fintech mobile app",
    "Product catalog service with full-text search and category filtering",
    "GDPR consent management module with audit log",
    "Kubernetes deployment pipeline with blue-green release strategy",
]


def vector_norm(vec: list[float]) -> float:
    return sum(x * x for x in vec) ** 0.5


def benchmark(name: str, embed_fn: Callable[[str], list[float]], texts: list[str]) -> dict[str, float | int | str]:
    """Run an embedding function over texts and return latency/vector metrics."""
    start = time.perf_counter()
    embeddings = [embed_fn(text) for text in texts]
    elapsed = time.perf_counter() - start

    if not embeddings:
        raise ValueError("No embeddings were generated")

    return {
        "model": name,
        "n_texts": len(texts),
        "total_seconds": round(elapsed, 3),
        "per_text_ms": round((elapsed / len(texts)) * 1000, 1),
        "dimensions": len(embeddings[0]),
        "first_embedding_norm": round(vector_norm(embeddings[0]), 4),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark OpenAI and local sentence-transformer embeddings.")
    parser.add_argument(
        "--model",
        default="text-embedding-3-small",
        help="OpenAI embedding model.",
    )
    parser.add_argument(
        "--dimensions",
        type=int,
        default=1536,
        help="Dimensions requested from OpenAI embeddings endpoint.",
    )
    parser.add_argument(
        "--skip-local",
        action="store_true",
        help="Skip local MiniLM benchmark.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.dimensions <= 0:
        print("ERROR: --dimensions must be > 0", file=sys.stderr)
        return 1

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        return 1

    client = OpenAI(api_key=settings.openai_api_key)

    def embed_openai(text: str, dimensions: int) -> list[float]:
        response = client.embeddings.create(
            model=args.model,
            input=text,
            dimensions=dimensions,
        )
        return response.data[0].embedding

    results: list[dict[str, float | int | str]] = []

    try:
        results.append(
            benchmark(
                f"{args.model}-{args.dimensions}d",
                lambda text: embed_openai(text, dimensions=args.dimensions),
                DEFAULT_TEXTS,
            )
        )

        if args.dimensions != 256:
            results.append(
                benchmark(
                    f"{args.model}-256d",
                    lambda text: embed_openai(text, dimensions=256),
                    DEFAULT_TEXTS,
                )
            )

        if not args.skip_local:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError:
                print(
                    "WARN: sentence-transformers not installed; skipping local benchmark. "
                    "Install with: uv add sentence-transformers",
                    file=sys.stderr,
                )
            else:
                local_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

                def embed_local_minilm(text: str) -> list[float]:
                    embedding = local_model.encode(text, normalize_embeddings=True)
                    return embedding.tolist()

                results.append(
                    benchmark(
                        "local-minilm-l6-v2",
                        embed_local_minilm,
                        DEFAULT_TEXTS,
                    )
                )

        for result in results:
            print(result)

        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())