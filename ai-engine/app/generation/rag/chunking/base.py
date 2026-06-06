from __future__ import annotations

from typing import Protocol

from app.generation.rag.schemas import Budget, Chunk


class BudgetChunker(Protocol):
    """Contract for chunkers that transform budgets into chunks."""

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        ...
