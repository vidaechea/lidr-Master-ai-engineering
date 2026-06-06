from __future__ import annotations

from app.generation.rag.analysis.similarity import cosine_similarity


def rank_by_similarity(
    *,
    query_embedding: list[float],
    candidates: list[tuple[str, str, list[float]]],
    top_k: int = 5,
) -> list[tuple[str, str, float]]:
    """Rank (id, payload, embedding) candidates by cosine similarity."""
    if top_k < 1:
        raise ValueError("top_k must be >= 1")

    scored = [
        (item_id, payload, cosine_similarity(query_embedding, embedding))
        for item_id, payload, embedding in candidates
    ]
    scored.sort(key=lambda item: item[2], reverse=True)
    return scored[:top_k]
