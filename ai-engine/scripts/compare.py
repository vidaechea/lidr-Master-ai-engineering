#!/usr/bin/env python3
"""CLI script to calculate cosine similarity between two text embeddings.

Usage:
    python scripts/compare.py --text-a "text 1" --text-b "text 2"

This script:
1. Takes two texts via command-line arguments
2. Generates embeddings using OpenAIEmbedder
3. Calculates cosine similarity manually (dot product / norm product)
4. Outputs results in a clean format
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.embedding_pipeline.embedder import OpenAIEmbedder  # noqa: E402


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Calculate cosine similarity between two vectors manually.

    Cosine similarity = (a · b) / (||a|| * ||b||)
    where:
    - a · b is the dot product
    - ||a|| and ||b|| are the Euclidean norms (magnitudes)

    Args:
        vec_a: First vector (embedding).
        vec_b: Second vector (embedding).

    Returns:
        Cosine similarity score between -1 and 1 (typically 0 to 1 for embeddings).

    Raises:
        ValueError: If vectors have different lengths.
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(f"Vector dimensions must match: {len(vec_a)} != {len(vec_b)}")

    # Dot product: sum of element-wise products
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))

    # Norm of vec_a: sqrt(sum of squares)
    norm_a = math.sqrt(sum(a * a for a in vec_a))

    # Norm of vec_b: sqrt(sum of squares)
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    # Handle zero vectors
    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot_product / (norm_a * norm_b)


def main() -> int:
    """Main entry point for the compare CLI script."""
    parser = argparse.ArgumentParser(
        description="Calculate cosine similarity between two text embeddings."
    )
    parser.add_argument(
        "--text-a",
        required=True,
        help="First text to embed.",
    )
    parser.add_argument(
        "--text-b",
        required=True,
        help="Second text to embed.",
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.text_a.strip():
        print("ERROR: --text-a must not be empty", file=sys.stderr)
        return 1

    if not args.text_b.strip():
        print("ERROR: --text-b must not be empty", file=sys.stderr)
        return 1

    # Check for API key
    if not settings.openai_api_key:
        print(
            "ERROR: OPENAI_API_KEY environment variable not set",
            file=sys.stderr,
        )
        return 1

    try:
        # Initialize embedder and embed both texts
        embedder = OpenAIEmbedder()
        embedding_a = embedder.embed_one(args.text_a)
        embedding_b = embedder.embed_one(args.text_b)

        # Calculate cosine similarity
        similarity = cosine_similarity(embedding_a, embedding_b)

        # Output results
        print(f"Text A: {args.text_a}")
        print(f"Text B: {args.text_b}")
        print(f"Cosine similarity: {similarity:.4f}")

        return 0

    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
