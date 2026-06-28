from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.store.repository import ChunkStore


@dataclass
class _Row:
    id: int
    document_id: int = 1
    chunk_type: str = "budget_component"
    content: str = "content"
    distance: float = 0.1
    metadata_: dict | None = None

    def __post_init__(self) -> None:
        if self.metadata_ is None:
            self.metadata_ = {}


def test_rrf_fusion_prioritizes_items_present_in_both_branches() -> None:
    vector_rows = [_Row(id=1), _Row(id=2), _Row(id=3)]
    lexical_rows = [_Row(id=3), _Row(id=1), _Row(id=4)]

    fused = ChunkStore._rrf_fuse_rows(
        vector_rows=vector_rows,
        lexical_rows=lexical_rows,
        k=3,
        rrf_k=60,
    )

    fused_ids = [row.id for row in fused]
    assert fused_ids[0] in {1, 3}
    assert set(fused_ids).issuperset({1, 3})


@pytest.mark.asyncio
async def test_search_raises_when_rerank_requested_and_reranker_missing() -> None:
    class _Embedder:
        def embed_one(self, text: str) -> list[float]:
            return [0.1, 0.2, 0.3]

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    def _session_factory():
        return _Session()

    retriever = SemanticRetriever(
        embedder=_Embedder(),
        session_factory=_session_factory,
        store=ChunkStore(),
        reranker=None,
    )

    with pytest.raises(RuntimeError, match="Reranking requested"):
        await retriever.search(query="test", k=5, mode="vector", rerank=True)
