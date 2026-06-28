from __future__ import annotations

from dataclasses import dataclass
import threading
import time

import structlog

log = structlog.get_logger(__name__)


@dataclass(slots=True)
class RerankCandidate:
    """Candidate item for cross-encoder reranking."""

    item_id: int
    text: str


@dataclass(slots=True)
class RerankResult:
    """Reranked candidate with relevance score."""

    item_id: int
    score: float


class CrossEncoderReranker:
    """Thin wrapper around sentence-transformers CrossEncoder.

    The model is loaded lazily at construction and can be disabled from config
    by not instantiating this service in dependencies.
    """

    def __init__(self, *, model_name: str) -> None:
        self._model_name = model_name
        self._model = None
        self._load_lock = threading.Lock()
        log.info("reranker_initialized", model_name=model_name, lazy_load=True)

    @property
    def model_name(self) -> str:
        return self._model_name

    def _ensure_loaded(self):
        if self._model is not None:
            return self._model

        with self._load_lock:
            if self._model is not None:
                return self._model

            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers is required for reranking. "
                    "Install it with: uv add sentence-transformers"
                ) from exc

            started = time.perf_counter()
            self._model = CrossEncoder(self._model_name)
            log.info(
                "reranker_loaded",
                model_name=self._model_name,
                load_ms=int((time.perf_counter() - started) * 1000),
            )
            return self._model

    def load(self) -> None:
        """Eagerly load model weights (useful for startup warmup/preflight checks)."""
        _ = self._ensure_loaded()

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int,
    ) -> list[RerankResult]:
        """Score (query, candidate) pairs and return top-k by descending relevance."""
        if top_k < 1:
            raise ValueError("top_k must be >= 1")
        if not candidates:
            return []

        model = self._ensure_loaded()
        pairs = [(query, candidate.text) for candidate in candidates]
        started = time.perf_counter()
        scores = model.predict(pairs)
        log.info(
            "reranker_scored",
            model_name=self._model_name,
            pairs=len(pairs),
            elapsed_ms=int((time.perf_counter() - started) * 1000),
        )

        scored = [
            RerankResult(item_id=candidate.item_id, score=float(score))
            for candidate, score in zip(candidates, scores)
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


__all__ = [
    "CrossEncoderReranker",
    "RerankCandidate",
    "RerankResult",
]
