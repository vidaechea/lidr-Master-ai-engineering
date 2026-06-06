from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(slots=True)
class StoredEmbedding:
    item_id: str
    payload: str
    embedding: list[float]


class VectorStore(Protocol):
    def upsert(self, items: list[StoredEmbedding]) -> None:
        ...

    def all(self) -> list[StoredEmbedding]:
        ...


class InMemoryVectorStore:
    """Simple vector store used for local smoke tests and demos."""

    def __init__(self) -> None:
        self._items: dict[str, StoredEmbedding] = {}

    def upsert(self, items: list[StoredEmbedding]) -> None:
        for item in items:
            self._items[item.item_id] = item

    def all(self) -> list[StoredEmbedding]:
        return list(self._items.values())


__all__ = ["StoredEmbedding", "VectorStore", "InMemoryVectorStore"]