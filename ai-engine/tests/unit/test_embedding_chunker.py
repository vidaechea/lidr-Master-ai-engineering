from __future__ import annotations

import pytest

from app.embedding_pipeline.chunker import chunk_text


def test_chunk_text_raises_when_overlap_is_not_smaller_than_chunk_size() -> None:
    with pytest.raises(ValueError, match="chunk_overlap must be smaller than chunk_size"):
        chunk_text(text="abcdef", chunk_size=4, chunk_overlap=4)


@pytest.mark.parametrize("text", ["", "   ", "\n\t "])
def test_chunk_text_returns_empty_for_blank_input(text: str) -> None:
    assert chunk_text(text=text, chunk_size=5, chunk_overlap=1) == []


def test_chunk_text_builds_expected_sliding_windows() -> None:
    result = chunk_text(text="abcdefghij", chunk_size=4, chunk_overlap=1)
    assert result == ["abcd", "defg", "ghij", "j"]
