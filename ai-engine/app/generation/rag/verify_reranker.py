"""Pre-flight check for the cross-encoder reranker.

Run before retrieval evaluations that enable reranking:

    uv run python -m app.generation.rag.verify_reranker

Exit code:
- 0: model loaded and sanity ranking passed
- 1: model failed to load/score
- 2: model loaded but ranking sanity check failed
"""

from __future__ import annotations

import sys

from app.generation.rag.reranker import CrossEncoderReranker, RerankCandidate

_QUERY = "e-commerce checkout and shopping cart platform"
_RELEVANT_DOC = "Online store checkout flow with shopping cart, payments and order management."
_IRRELEVANT_DOC = "Hospital appointment scheduling and telemedicine consultations."


def main() -> int:
    reranker = CrossEncoderReranker(model_name="cross-encoder/ms-marco-MiniLM-L-6-v2")
    print(f"Loading reranker model: {reranker.model_name!r} ...")

    try:
        ranked = reranker.rerank(
            query=_QUERY,
            candidates=[
                RerankCandidate(item_id=1, text=_RELEVANT_DOC),
                RerankCandidate(item_id=2, text=_IRRELEVANT_DOC),
            ],
            top_k=2,
        )
    except Exception as exc:
        print(f"ERROR: reranker preflight failed: {exc}", file=sys.stderr)
        return 1

    ordered_ids = [item.item_id for item in ranked]
    print(f"Ranked ids: {ordered_ids}")

    if not ordered_ids or ordered_ids[0] != 1:
        print(
            "WARNING: relevant document did not rank first. Verify model configuration.",
            file=sys.stderr,
        )
        return 2

    print("OK: reranker loaded and ranked the relevant document first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
