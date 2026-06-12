from __future__ import annotations

from dataclasses import dataclass

from app.generation.rag.chunking.base import BudgetChunker
from app.generation.rag.embedding.embedder import EMBEDDING_COST_PER_MILLION_TOKENS_USD, EMBEDDING_MODEL, embed_texts
from app.generation.rag.schemas import CompareHit, CompareQueryResult, StrategyStats, Budget, Chunk
from app.generation.rag.analysis.similarity import cosine_similarity


DEFAULT_STRATEGIES: tuple[str, ...] = (
    "structural",
    "fixed_size",
    "recursive",
    "sentence_window",
    "semantic",
    "propositional",
    "contextual_retrieval",
    "hierarchical",
)


@dataclass(frozen=True)
class _EmbeddedStrategyData:
    chunks: list[Chunk]
    vectors: list[list[float]]


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


class ChunkingComparator:
    """Compare multiple chunkers over the same budget corpus and semantic queries."""

    def __init__(self, chunkers: dict[str, BudgetChunker]) -> None:
        self._chunkers = chunkers
        self._cache: dict[str, _EmbeddedStrategyData] = {}

    def compute_stats(self, budgets: list[Budget]) -> dict[str, StrategyStats]:
        stats: dict[str, StrategyStats] = {}
        for name in self._chunkers:
            data = self._embedded_strategy(name, budgets)
            token_counts = [chunk.token_count for chunk in data.chunks]
            total_chunks = len(token_counts)
            total_tokens = sum(token_counts)
            stats[name] = StrategyStats(
                total_chunks=total_chunks,
                total_tokens=total_tokens,
                avg_tokens_per_chunk=(total_tokens / total_chunks) if total_chunks else 0.0,
                min_tokens=min(token_counts) if token_counts else 0,
                max_tokens=max(token_counts) if token_counts else 0,
                estimated_cost_usd=(total_tokens * EMBEDDING_COST_PER_MILLION_TOKENS_USD) / 1_000_000,
            )
        return stats

    def run_queries(
        self,
        budgets: list[Budget],
        queries: list[str],
        top_k: int,
    ) -> dict[str, list[CompareQueryResult]]:
        results: dict[str, list[CompareQueryResult]] = {}
        if not queries:
            return {name: [] for name in self._chunkers}

        query_vectors = embed_texts(texts=queries, model=EMBEDDING_MODEL)
        for name in self._chunkers:
            data = self._embedded_strategy(name, budgets)
            candidate_map = {chunk.chunk_id: chunk for chunk in data.chunks}
            candidates = [
                (chunk.chunk_id, chunk.text, vector)
                for chunk, vector in zip(data.chunks, data.vectors)
            ]
            strategy_results: list[CompareQueryResult] = []
            for query, query_vector in zip(queries, query_vectors):
                ranked = rank_by_similarity(
                    query_embedding=query_vector,
                    candidates=candidates,
                    top_k=top_k,
                )
                strategy_results.append(
                    CompareQueryResult(
                        query=query,
                        results=[
                            CompareHit(
                                chunk_id=chunk_id,
                                payload=payload,
                                similarity=similarity,
                                metadata=candidate_map[chunk_id].metadata,
                            )
                            for chunk_id, payload, similarity in ranked
                        ],
                    )
                )
            results[name] = strategy_results
        return results

    def _embedded_strategy(self, name: str, budgets: list[Budget]) -> _EmbeddedStrategyData:
        if name in self._cache:
            return self._cache[name]

        chunks = self._chunkers[name].chunk(budgets)
        vectors = embed_texts(texts=[chunk.text for chunk in chunks], model=EMBEDDING_MODEL) if chunks else []
        data = _EmbeddedStrategyData(chunks=chunks, vectors=vectors)
        self._cache[name] = data
        return data
