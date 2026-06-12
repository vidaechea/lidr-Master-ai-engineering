from __future__ import annotations

import json

import tiktoken

from app.generation.rag.chunking.base import BudgetChunker
from app.generation.rag.chunking.structural import chunk_text
from app.generation.rag.schemas import Budget, Chunk


class FixedSizeBudgetChunker(BudgetChunker):
    """Serialize each budget and chunk it with a fixed-size sliding window."""

    def __init__(self, *, chunk_size: int = 600, chunk_overlap: int = 120) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._encoder = tiktoken.encoding_for_model("text-embedding-3-small")

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            serialized = json.dumps(budget.model_dump(mode="json"), ensure_ascii=True)
            windows = chunk_text(
                text=serialized,
                chunk_size=self._chunk_size,
                chunk_overlap=self._chunk_overlap,
            )
            for index, window in enumerate(windows):
                chunks.append(
                    Chunk(
                        chunk_id=f"{budget.budget_id}::window::{index}",
                        text=window,
                        metadata={
                            "budget_id": budget.budget_id,
                            "strategy": "fixed_size",
                            "window_index": index,
                        },
                        token_count=len(self._encoder.encode(window)),
                    )
                )
        return chunks
