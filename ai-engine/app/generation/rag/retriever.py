from __future__ import annotations

from dataclasses import dataclass

from app.generation.rag.analysis.comparison import rank_by_similarity


@dataclass(slots=True)
class RetrievalCandidate:
    """Candidate item with precomputed embedding for retrieval."""

    item_id: str
    payload: str
    embedding: list[float]


@dataclass(slots=True)
class RetrievalResult:
    """Single retrieval result ranked by similarity."""

    item_id: str
    payload: str
    similarity: float


class RAGRetriever:
    """In-memory retriever over embedded candidates."""

    def retrieve(
        self,
        *,
        query_embedding: list[float],
        candidates: list[RetrievalCandidate],
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        ranked = rank_by_similarity(
            query_embedding=query_embedding,
            candidates=[(c.item_id, c.payload, c.embedding) for c in candidates],
            top_k=top_k,
        )
        return [
            RetrievalResult(item_id=item_id, payload=payload, similarity=score)
            for item_id, payload, score in ranked
        ]


__all__ = ["RAGRetriever", "RetrievalCandidate", "RetrievalResult"]