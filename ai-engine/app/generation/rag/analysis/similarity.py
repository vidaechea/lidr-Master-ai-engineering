from __future__ import annotations

import math


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity in [0, 1] for two vectors."""
    if len(left) != len(right):
        raise ValueError("Vectors must have the same dimension")

    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))

    if left_norm <= 1e-12 or right_norm <= 1e-12:
        return 0.0

    similarity = dot / (left_norm * right_norm)
    return max(0.0, min(1.0, similarity))
