#!/usr/bin/env python3
"""Compare semantic similarity across predefined text pairs.

Usage:
    python scripts/compare_pairs.py
    python scripts/compare_pairs.py --model text-embedding-3-large
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from openai import OpenAI

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Returns a value in [-1, 1]. For text embeddings from modern models,
    values typically fall in [0, 1].
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have the same dimensionality")

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        raise ValueError("Cannot compute similarity for zero-norm vectors")

    return dot / (norm_a * norm_b)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare similarity for predefined text pairs.")
    parser.add_argument(
        "--model",
        default="text-embedding-3-small",
        help="Embedding model to use.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if not settings.openai_api_key:
        print("ERROR: OPENAI_API_KEY environment variable not set", file=sys.stderr)
        return 1

    client = OpenAI(api_key=settings.openai_api_key)

    def embed(text: str) -> list[float]:
        response = client.embeddings.create(
            model=args.model,
            input=text,
        )
        return response.data[0].embedding

    pairs = [
        # Pair 1: technically close, different wording
        (
            "User authentication API with role-based access control",
            "Login service backend with permission management",
        ),
        # Pair 2: unrelated, same domain (web backend)
        (
            "User authentication API with role-based access control",
            "Real-time WebSocket chat module with message persistence",
        ),
        # Pair 3: generic, ambiguous overlap
        (
            "Performance optimization for high-traffic endpoints",
            "Caching strategy for database-heavy queries",
        ),
    ]

    try:
        print(f"Model: {args.model}")
        print()
        for text_a, text_b in pairs:
            vec_a = embed(text_a)
            vec_b = embed(text_b)
            sim = cosine_similarity(vec_a, vec_b)
            print(f"Similarity: {sim:.4f}")
            print(f"  A: {text_a}")
            print(f"  B: {text_b}")
            print()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())