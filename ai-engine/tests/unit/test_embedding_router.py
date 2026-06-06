from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException

from app.embedding_pipeline.router import build_chunks, build_embeddings
from app.embedding_pipeline.schemas import ChunkRequest, EmbedRequest

router_module = importlib.import_module("app.embedding_pipeline.router")


def test_build_chunks_returns_indexed_chunks() -> None:
    payload = ChunkRequest(text=("abcdefghij" * 22), chunk_size=100, chunk_overlap=20)

    response = build_chunks(payload)

    assert [item.index for item in response.chunks] == [0, 1, 2]
    assert [len(item.text) for item in response.chunks] == [100, 100, 60]


def test_build_chunks_returns_http_400_on_invalid_overlap() -> None:
    payload = ChunkRequest(text="abcde", chunk_size=100, chunk_overlap=100)

    with pytest.raises(HTTPException) as exc_info:
        build_chunks(payload)

    assert exc_info.value.status_code == 400
    assert "chunk_overlap must be smaller than chunk_size" in str(exc_info.value.detail)


def test_build_embeddings_strips_empty_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_embed_texts(texts: list[str], model: str) -> list[list[float]]:
        captured["texts"] = texts
        captured["model"] = model
        return [[0.11, 0.22], [0.33, 0.44]]

    monkeypatch.setattr(router_module, "embed_texts", fake_embed_texts)

    payload = EmbedRequest(texts=["  alfa  ", "", "  ", "beta"], model="text-embedding-3-small")
    response = build_embeddings(payload)

    assert captured["texts"] == ["alfa", "beta"]
    assert captured["model"] == "text-embedding-3-small"
    assert response.model == "text-embedding-3-small"
    assert [item.index for item in response.embeddings] == [0, 1]
    assert [item.vector for item in response.embeddings] == [[0.11, 0.22], [0.33, 0.44]]


def test_build_embeddings_returns_http_400_when_all_texts_are_empty() -> None:
    payload = EmbedRequest(texts=["", " ", "\n"], model="text-embedding-3-small")

    with pytest.raises(HTTPException) as exc_info:
        build_embeddings(payload)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "At least one non-empty text is required"


def test_build_embeddings_returns_http_400_on_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        raise ValueError("OPENAI_API_KEY is required for embedding generation")

    monkeypatch.setattr(router_module, "embed_texts", fail_embed_texts)

    payload = EmbedRequest(texts=["hola"], model="text-embedding-3-small")
    with pytest.raises(HTTPException) as exc_info:
        build_embeddings(payload)

    assert exc_info.value.status_code == 400
    assert "OPENAI_API_KEY is required" in str(exc_info.value.detail)


def test_build_embeddings_returns_http_500_on_unexpected_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_embed_texts(*, texts: list[str], model: str) -> list[list[float]]:
        raise RuntimeError("service unavailable")

    monkeypatch.setattr(router_module, "embed_texts", fail_embed_texts)

    payload = EmbedRequest(texts=["hola"], model="text-embedding-3-small")
    with pytest.raises(HTTPException) as exc_info:
        build_embeddings(payload)

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Internal processing error"
