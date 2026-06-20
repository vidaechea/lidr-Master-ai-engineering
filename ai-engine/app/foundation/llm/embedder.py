from __future__ import annotations

import sys

from app.generation.rag.embedding import embedder as _rag_embedder

# Keep this legacy import path as an alias to the canonical RAG embedder module.
# This preserves monkeypatch targets like app.foundation.llm.embedder.OpenAI.
sys.modules[__name__] = _rag_embedder

