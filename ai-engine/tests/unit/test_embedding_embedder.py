from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.embedding_pipeline import embedder


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
