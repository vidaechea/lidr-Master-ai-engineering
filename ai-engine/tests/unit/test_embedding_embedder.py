from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from app.foundation.llm import embedder
from app.domain.schemas.embeddings import Chunk, EmbeddedChunk


def test_embed_texts_raises_when_openai_api_key_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedder.settings, "openai_api_key", None)

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        embedder.embed_texts(texts=["hola"], model="text-embedding-3-small")


def test_embed_texts_returns_vectors_from_openai_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            captured["api_key"] = api_key

            def create(*, model: str, input: list[str]) -> SimpleNamespace:
                captured["model"] = model
                captured["input"] = input
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(embedding=[0.1, 0.2]),
                        SimpleNamespace(embedding=[0.3, 0.4]),
                    ]
                )

            self.embeddings = SimpleNamespace(create=create)

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    result = embedder.embed_texts(texts=["a", "b"], model="text-embedding-3-small")

    assert captured["api_key"] == "test-key"
    assert captured["model"] == "text-embedding-3-small"
    assert captured["input"] == ["a", "b"]
    assert result == [[0.1, 0.2], [0.3, 0.4]]


# ============================================================================
# OpenAIEmbedder Tests
# ============================================================================


def test_openai_embedder_init_raises_when_api_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that OpenAIEmbedder initialization raises when OPENAI_API_KEY is missing."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", None)

    with pytest.raises(ValueError, match="OPENAI_API_KEY is required"):
        embedder.OpenAIEmbedder()


def test_openai_embedder_init_succeeds_with_valid_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that OpenAIEmbedder initializes successfully with valid API key."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            self.api_key = api_key

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()
    assert emb._client is not None


def test_openai_embedder_embed_one_raises_on_empty_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that embed_one raises ValueError when text is empty."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            pass

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()

    with pytest.raises(ValueError, match="Text must be non-empty"):
        emb.embed_one("")

    with pytest.raises(ValueError, match="Text must be non-empty"):
        emb.embed_one("   ")


def test_openai_embedder_embed_one_returns_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that embed_one returns embedding vector from OpenAI."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            def create(*, model: str, input: list[str]) -> SimpleNamespace:
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
                )

            self.embeddings = SimpleNamespace(create=create)

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()
    result = emb.embed_one("test text")

    assert result == [0.1, 0.2, 0.3]


def test_openai_embedder_embed_many_raises_on_empty_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that embed_many raises ValueError when chunks list is empty."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            pass

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()

    with pytest.raises(ValueError, match="Chunks list must not be empty"):
        emb.embed_many([])


def test_openai_embedder_embed_many_processes_single_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that embed_many processes chunks in correct batch and returns EmbeddedChunk objects."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    chunks = [
        Chunk(chunk_id="c1", text="text1", metadata={}, token_count=10),
        Chunk(chunk_id="c2", text="text2", metadata={}, token_count=20),
    ]

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            def create(*, model: str, input: list[str]) -> SimpleNamespace:
                return SimpleNamespace(
                    data=[
                        SimpleNamespace(embedding=[0.1, 0.2]),
                        SimpleNamespace(embedding=[0.3, 0.4]),
                    ]
                )

            self.embeddings = SimpleNamespace(create=create)

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()
    result = emb.embed_many(chunks)

    assert len(result) == 2
    assert isinstance(result[0], EmbeddedChunk)
    assert isinstance(result[1], EmbeddedChunk)
    assert result[0].chunk_id == "c1"
    assert result[0].embedding == [0.1, 0.2]
    assert result[1].chunk_id == "c2"
    assert result[1].embedding == [0.3, 0.4]


def test_openai_embedder_embed_many_creates_multiple_batches(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that embed_many splits chunks into batches correctly."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    # Create 250 chunks (will be split into 3 batches: 100 + 100 + 50)
    chunks = [
        Chunk(chunk_id=f"c{i}", text=f"text{i}", metadata={}, token_count=1)
        for i in range(250)
    ]

    create_calls = []

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            def create(*, model: str, input: list[str]) -> SimpleNamespace:
                create_calls.append(len(input))
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.1] * i) for i in range(1, len(input) + 1)]
                )

            self.embeddings = SimpleNamespace(create=create)

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()
    result = emb.embed_many(chunks)

    assert len(result) == 250
    assert create_calls == [100, 100, 50]


def test_openai_embedder_embed_many_calculates_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that embed_many correctly calculates estimated cost."""
    monkeypatch.setattr(embedder.settings, "openai_api_key", "test-key")

    # Create chunks with total 1_000_000 tokens
    chunks = [
        Chunk(chunk_id="c1", text="text1", metadata={}, token_count=500_000),
        Chunk(chunk_id="c2", text="text2", metadata={}, token_count=500_000),
    ]

    class FakeOpenAI:
        def __init__(self, api_key: str) -> None:
            def create(*, model: str, input: list[str]) -> SimpleNamespace:
                return SimpleNamespace(
                    data=[SimpleNamespace(embedding=[0.1]) for _ in input]
                )

            self.embeddings = SimpleNamespace(create=create)

    monkeypatch.setattr(embedder, "OpenAI", FakeOpenAI)

    emb = embedder.OpenAIEmbedder()
    
    # Mock logging to capture the info call
    with patch("app.foundation.llm.embedder.log") as mock_log:
        emb.embed_many(chunks)
        
        # Verify that log.info was called with cost calculation
        log_calls = [call for call in mock_log.info.call_args_list 
                     if "embedding_complete" in str(call)]
        assert len(log_calls) > 0
        
        # Check cost calculation: 1_000_000 tokens * $0.02 / 1_000_000 = $0.02
        call_args = log_calls[0]
        assert call_args[1]["estimated_cost_usd"] == 0.02


def test_openai_embedder_calculate_cost_static_method() -> None:
    """Test that cost calculation static method works correctly."""
    # Test: 1,000 tokens * $0.02 / 1,000,000 = $0.00002
    cost = embedder.OpenAIEmbedder._calculate_cost(1_000)
    assert abs(cost - 0.00002) < 1e-10

    # Test: 1,000,000 tokens * $0.02 / 1,000,000 = $0.02
    cost = embedder.OpenAIEmbedder._calculate_cost(1_000_000)
    assert abs(cost - 0.02) < 1e-10

    # Test: 0 tokens
    cost = embedder.OpenAIEmbedder._calculate_cost(0)
    assert cost == 0.0

