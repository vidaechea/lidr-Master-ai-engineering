from __future__ import annotations

import time

import structlog
from openai import OpenAI, RateLimitError

from app.config import settings
from app.generation.rag.schemas import Chunk, EmbeddedChunk

log = structlog.get_logger(__name__)

# OpenAI text-embedding-3-small pricing: $0.02 per 1 million tokens
EMBEDDING_COST_PER_MILLION_TOKENS_USD = 0.02
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSION = 1536
BATCH_SIZE = 100
MAX_RETRIES = 3
RETRY_DELAYS = [1, 2, 4]  # seconds


def embed_texts(texts: list[str], model: str) -> list[list[float]]:
    """Generate embeddings with OpenAI for a list of input strings."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for embedding generation")

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]


class OpenAIEmbedder:
    """Embeddings service using OpenAI's text-embedding-3-small model."""

    def __init__(self) -> None:
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is required for embedder initialization")
        self._client = OpenAI(api_key=settings.openai_api_key)
        log.info("openai_embedder_initialized", model=EMBEDDING_MODEL, dimension=EMBEDDING_DIMENSION)

    def embed_one(self, text: str) -> list[float]:
        """Embed a single text string."""
        if not text or not text.strip():
            raise ValueError("Text must be non-empty")

        try:
            response = self._client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=[text.strip()],
            )
            return response.data[0].embedding
        except RateLimitError as exc:
            log.error("rate_limit_error_embed_one", detail=str(exc))
            raise

    def embed_many(self, chunks: list[Chunk]) -> list[EmbeddedChunk]:
        """Embed multiple chunks in batches with exponential retry on rate limits."""
        if not chunks:
            raise ValueError("Chunks list must not be empty")

        total_input_tokens = sum(chunk.token_count for chunk in chunks)
        estimated_cost = self._calculate_cost(total_input_tokens)

        embedded_chunks: list[EmbeddedChunk] = []

        for batch_num, batch_chunks in self._iter_batches(chunks):
            vectors = self._embed_batch_with_retry(batch_num=batch_num, batch_chunks=batch_chunks)
            embedded_chunks.extend(self._to_embedded_chunks(batch_chunks=batch_chunks, vectors=vectors))

        log.info(
            "embedding_complete",
            total_chunks=len(chunks),
            total_tokens=total_input_tokens,
            estimated_cost_usd=round(estimated_cost, 6),
        )

        return embedded_chunks

    @staticmethod
    def _iter_batches(chunks: list[Chunk]) -> list[tuple[int, list[Chunk]]]:
        batches: list[tuple[int, list[Chunk]]] = []
        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch_end = min(batch_start + BATCH_SIZE, len(chunks))
            batch_chunks = chunks[batch_start:batch_end]
            batch_num = batch_start // BATCH_SIZE + 1
            batches.append((batch_num, batch_chunks))
        return batches

    def _embed_batch_with_retry(self, *, batch_num: int, batch_chunks: list[Chunk]) -> list[list[float]]:
        batch_texts = [chunk.text for chunk in batch_chunks]
        batch_size = len(batch_chunks)
        batch_tokens = sum(chunk.token_count for chunk in batch_chunks)

        last_error: RateLimitError | None = None
        for attempt in range(MAX_RETRIES):
            try:
                start_time = time.perf_counter()
                response = self._client.embeddings.create(
                    model=EMBEDDING_MODEL,
                    input=batch_texts,
                )
                elapsed = time.perf_counter() - start_time
                vectors = [item.embedding for item in response.data]

                log.info(
                    "embedding_batch_processed",
                    batch_num=batch_num,
                    batch_size=batch_size,
                    batch_tokens=batch_tokens,
                    latency_seconds=round(elapsed, 3),
                )
                return vectors
            except RateLimitError as exc:
                last_error = exc
                self._handle_retry(batch_num=batch_num, attempt=attempt)

        raise last_error or RateLimitError("Failed to embed batch after retries")

    @staticmethod
    def _handle_retry(*, batch_num: int, attempt: int) -> None:
        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            log.warning(
                "rate_limit_retry",
                batch_num=batch_num,
                attempt=attempt + 1,
                delay_seconds=delay,
            )
            time.sleep(delay)
            return

        log.error(
            "rate_limit_max_retries_exceeded",
            batch_num=batch_num,
            max_retries=MAX_RETRIES,
        )

    @staticmethod
    def _to_embedded_chunks(
        *,
        batch_chunks: list[Chunk],
        vectors: list[list[float]],
    ) -> list[EmbeddedChunk]:
        return [
            EmbeddedChunk(
                chunk_id=chunk.chunk_id,
                text=chunk.text,
                metadata=chunk.metadata,
                token_count=chunk.token_count,
                embedding=vector,
            )
            for chunk, vector in zip(batch_chunks, vectors)
        ]

    @staticmethod
    def _calculate_cost(input_tokens: int) -> float:
        """Calculate estimated cost in USD for embedding tokens."""
        return (input_tokens * EMBEDDING_COST_PER_MILLION_TOKENS_USD) / 1_000_000

__all__ = [
    "BATCH_SIZE",
    "EMBEDDING_COST_PER_MILLION_TOKENS_USD",
    "EMBEDDING_DIMENSION",
    "EMBEDDING_MODEL",
    "MAX_RETRIES",
    "RETRY_DELAYS",
    "OpenAIEmbedder",
    "embed_texts",
]
