from __future__ import annotations

import re

import tiktoken

from app.generation.rag.chunking.base import BudgetChunker
from app.generation.rag.chunking.structural import chunk_text
from app.generation.rag.schemas import Budget, BudgetComponent, Chunk


class _BaseStrategyChunker(BudgetChunker):
    """Shared helpers for strategy implementations."""

    def __init__(self) -> None:
        self._encoder = tiktoken.encoding_for_model("text-embedding-3-small")

    def _tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))

    @staticmethod
    def _budget_context(budget: Budget) -> str:
        return (
            f"Budget {budget.budget_id} | "
            f"Client: {budget.client_metadata.name} ({budget.client_metadata.sector}) | "
            f"Main tech: {budget.main_technology} | "
            f"Hours: {budget.total_estimated_hours}"
        )

    @staticmethod
    def _component_text(component: BudgetComponent) -> str:
        stack = ", ".join(component.tech_stack) if component.tech_stack else "n/a"
        deps = ", ".join(component.dependencies) if component.dependencies else "none"
        return (
            f"Component {component.component_id}: {component.name}. "
            f"Description: {component.description}. "
            f"Complexity: {component.complexity}. "
            f"Estimated hours: {component.estimated_hours}. "
            f"Tech stack: {stack}. "
            f"Dependencies: {deps}."
        )


class RecursiveBudgetChunker(_BaseStrategyChunker):
    """Recursive-like splitter over component text using tighter windows."""

    def __init__(self, *, chunk_size: int = 420, chunk_overlap: int = 80) -> None:
        super().__init__()
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            context = self._budget_context(budget)
            for component in budget.components:
                source = f"{context}. {self._component_text(component)}"
                windows = chunk_text(
                    text=source,
                    chunk_size=self._chunk_size,
                    chunk_overlap=self._chunk_overlap,
                )
                for index, window in enumerate(windows):
                    chunks.append(
                        Chunk(
                            chunk_id=f"{budget.budget_id}::recursive::{component.component_id}::{index}",
                            text=window,
                            metadata={
                                "budget_id": budget.budget_id,
                                "component_id": component.component_id,
                                "strategy": "recursive",
                                "window_index": index,
                            },
                            token_count=self._tokens(window),
                        )
                    )
        return chunks


class SentenceWindowBudgetChunker(_BaseStrategyChunker):
    """Sentence-window chunker with stride to preserve local context."""

    def __init__(self, *, window_sentences: int = 3, stride: int = 2) -> None:
        super().__init__()
        self._window_sentences = max(1, window_sentences)
        self._stride = max(1, stride)

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            source = [self._budget_context(budget)] + [
                self._component_text(component) for component in budget.components
            ]
            sentences = [
                sentence.strip()
                for sentence in re.split(r"(?<=[.!?])\s+", " ".join(source).strip())
                if sentence.strip()
            ]
            if not sentences:
                continue

            index = 0
            while index < len(sentences):
                window = sentences[index : index + self._window_sentences]
                if not window:
                    break
                text = " ".join(window)
                chunks.append(
                    Chunk(
                        chunk_id=f"{budget.budget_id}::sentence_window::{index}",
                        text=text,
                        metadata={
                            "budget_id": budget.budget_id,
                            "strategy": "sentence_window",
                            "sentence_index": index,
                        },
                        token_count=self._tokens(text),
                    )
                )
                index += self._stride
        return chunks


class SemanticBudgetChunker(_BaseStrategyChunker):
    """Groups components by complexity as a semantic proxy."""

    _ORDER = ("high", "medium", "low")

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            context = self._budget_context(budget)
            grouped: dict[str, list[BudgetComponent]] = {level: [] for level in self._ORDER}
            for component in budget.components:
                grouped.setdefault(component.complexity, []).append(component)

            for level in self._ORDER:
                bucket = grouped.get(level, [])
                if not bucket:
                    continue
                lines = [f"{context}. Semantic group: {level} complexity."]
                for component in bucket:
                    lines.append(self._component_text(component))
                text = " ".join(lines)
                chunks.append(
                    Chunk(
                        chunk_id=f"{budget.budget_id}::semantic::{level}",
                        text=text,
                        metadata={
                            "budget_id": budget.budget_id,
                            "strategy": "semantic",
                            "complexity_group": level,
                            "components": [component.component_id for component in bucket],
                        },
                        token_count=self._tokens(text),
                    )
                )
        return chunks


class PropositionalBudgetChunker(_BaseStrategyChunker):
    """Builds proposition-style facts per component."""

    def __init__(self, *, model_name: str | None = None) -> None:
        super().__init__()
        self._model_name = model_name

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            context = self._budget_context(budget)
            for component in budget.components:
                stack = ", ".join(component.tech_stack) if component.tech_stack else "n/a"
                deps = ", ".join(component.dependencies) if component.dependencies else "none"
                text = "\n".join(
                    [
                        f"Project context: {context}",
                        f"Proposition: Component {component.component_id} is named '{component.name}'.",
                        f"Proposition: Work description is '{component.description}'.",
                        f"Proposition: Complexity is {component.complexity} with {component.estimated_hours} estimated hours.",
                        f"Proposition: Tech stack is {stack}.",
                        f"Proposition: Dependencies are {deps}.",
                    ]
                )
                chunks.append(
                    Chunk(
                        chunk_id=f"{budget.budget_id}::propositional::{component.component_id}",
                        text=text,
                        metadata={
                            "budget_id": budget.budget_id,
                            "component_id": component.component_id,
                            "strategy": "propositional",
                            "chunker_model": self._model_name,
                        },
                        token_count=self._tokens(text),
                    )
                )
        return chunks


class ContextualRetrievalBudgetChunker(_BaseStrategyChunker):
    """Adds rich global context prefix to each local chunk."""

    def __init__(
        self,
        *,
        chunk_size: int = 520,
        chunk_overlap: int = 100,
        model_name: str | None = None,
    ) -> None:
        super().__init__()
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._model_name = model_name

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            context = (
                f"Global context. Budget={budget.budget_id}; "
                f"Summary={budget.project_summary}; "
                f"Main technology={budget.main_technology}; "
                f"Total hours={budget.total_estimated_hours}."
            )
            for component in budget.components:
                base = self._component_text(component)
                windows = chunk_text(
                    text=base,
                    chunk_size=self._chunk_size,
                    chunk_overlap=self._chunk_overlap,
                )
                for index, window in enumerate(windows):
                    text = f"{context}\n\nLocal window: {window}"
                    chunks.append(
                        Chunk(
                            chunk_id=f"{budget.budget_id}::contextual_retrieval::{component.component_id}::{index}",
                            text=text,
                            metadata={
                                "budget_id": budget.budget_id,
                                "component_id": component.component_id,
                                "strategy": "contextual_retrieval",
                                "window_index": index,
                                "chunker_model": self._model_name,
                            },
                            token_count=self._tokens(text),
                        )
                    )
        return chunks


class HierarchicalBudgetChunker(_BaseStrategyChunker):
    """Emits parent and child chunks to preserve hierarchy."""

    def chunk(self, budgets: list[Budget]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for budget in budgets:
            parent_text = (
                f"Parent chunk for {budget.budget_id}. "
                f"Project summary: {budget.project_summary}. "
                f"Client: {budget.client_metadata.name} in {budget.client_metadata.sector}. "
                f"Main technology: {budget.main_technology}. "
                f"Total estimated hours: {budget.total_estimated_hours}."
            )
            parent_id = f"{budget.budget_id}::hierarchical::parent"
            chunks.append(
                Chunk(
                    chunk_id=parent_id,
                    text=parent_text,
                    metadata={
                        "budget_id": budget.budget_id,
                        "strategy": "hierarchical",
                        "level": "parent",
                    },
                    token_count=self._tokens(parent_text),
                )
            )

            for component in budget.components:
                child_text = self._component_text(component)
                chunks.append(
                    Chunk(
                        chunk_id=f"{budget.budget_id}::hierarchical::child::{component.component_id}",
                        text=child_text,
                        metadata={
                            "budget_id": budget.budget_id,
                            "component_id": component.component_id,
                            "strategy": "hierarchical",
                            "level": "child",
                            "parent_chunk_id": parent_id,
                        },
                        token_count=self._tokens(child_text),
                    )
                )
        return chunks
