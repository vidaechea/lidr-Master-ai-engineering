from __future__ import annotations

from openai import OpenAI

from app.config import settings


def embed_texts(texts: list[str], model: str) -> list[list[float]]:
    """Generate embeddings with OpenAI for a list of input strings."""
    if not settings.openai_api_key:
        raise ValueError("OPENAI_API_KEY is required for embedding generation")

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]
