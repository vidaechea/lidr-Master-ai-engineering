from __future__ import annotations

from pydantic import BaseModel, Field


class ChunkRequest(BaseModel):
    text: str = Field(min_length=1)
    chunk_size: int = Field(default=800, ge=100, le=8000)
    chunk_overlap: int = Field(default=100, ge=0, le=2000)


class ChunkItem(BaseModel):
    index: int
    text: str


class ChunkResponse(BaseModel):
    chunks: list[ChunkItem]


class EmbedRequest(BaseModel):
    texts: list[str] = Field(min_length=1)
    model: str = Field(default="text-embedding-3-small")


class EmbeddingItem(BaseModel):
    index: int
    vector: list[float]


class EmbedResponse(BaseModel):
    model: str
    embeddings: list[EmbeddingItem]
