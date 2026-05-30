from __future__ import annotations

import argparse
import math


def cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    if len(vector_a) != len(vector_b):
        raise ValueError("Vectors must have the same length")
    if not vector_a:
        raise ValueError("Vectors must not be empty")

    dot_product = sum(a * b for a, b in zip(vector_a, vector_b, strict=False))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))

    if norm_a == 0.0 or norm_b == 0.0:
        raise ValueError("Vectors must not be zero vectors")

    return dot_product / (norm_a * norm_b)


def parse_vector(raw: str) -> list[float]:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values:
        raise ValueError("Vector must include at least one numeric value")
    return [float(value) for value in values]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two vectors with cosine similarity")
    parser.add_argument("--a", required=True, help="Comma-separated vector A")
    parser.add_argument("--b", required=True, help="Comma-separated vector B")
    args = parser.parse_args()

    vector_a = parse_vector(args.a)
    vector_b = parse_vector(args.b)
    score = cosine_similarity(vector_a, vector_b)
    print(f"cosine_similarity={score:.6f}")


if __name__ == "__main__":
    main()
