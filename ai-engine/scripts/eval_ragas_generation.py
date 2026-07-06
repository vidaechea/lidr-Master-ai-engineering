#!/usr/bin/env python3
"""Evaluate RAG estimate generation quality with native RAGAS metrics.

Per query this runner builds the required RAGAS payload:
    question, answer, contexts, ground_truth

Then computes:
    faithfulness, answer_relevancy, context_precision, context_recall
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, cast

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402

_RAGAS_VERTEXAI_SHIM_PATH = "langchain_community.chat_models.vertexai"


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    question: str
    ground_truth: str


@dataclass(frozen=True)
class CitationStats:
    grounded_line_items: int
    ungrounded_line_items: int
    dangling_source_refs: int


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    answer_relevancy: float
    faithfulness: float
    context_precision: float
    context_recall: float
    grounded_line_items: int
    ungrounded_line_items: int
    dangling_source_refs: int

    @property
    def ragas_mean(self) -> float:
        return mean(
            [
                self.answer_relevancy,
                self.faithfulness,
                self.context_precision,
                self.context_recall,
            ]
        )


def _require_eval_dependencies() -> None:
    missing: list[str] = []
    for module_name in ("ragas", "datasets", "langchain_openai", "langchain_community"):
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    if missing:
        missing_csv = ", ".join(missing)
        raise SystemExit(
            "Missing evaluation dependencies: "
            f"{missing_csv}. Install them with `uv sync --extra evals` or "
            "`uv add --dev ragas datasets langchain-openai langchain-community`."
        )


def _require_openai_api_key() -> None:
    if os.getenv("OPENAI_API_KEY"):
        return
    if settings.openai_api_key:
        os.environ["OPENAI_API_KEY"] = settings.openai_api_key
        return
    raise SystemExit(
        "OPENAI_API_KEY is required for RAGAS evaluation (judge + embeddings)."
    )


def _ensure_ragas_import_compat() -> None:
    """Provide a minimal shim for ragas on environments missing legacy VertexAI path."""
    if _RAGAS_VERTEXAI_SHIM_PATH in sys.modules:
        return
    try:
        if importlib.util.find_spec(_RAGAS_VERTEXAI_SHIM_PATH) is not None:
            return
    except ValueError:
        # A partially initialized module can raise when __spec__ is missing.
        if _RAGAS_VERTEXAI_SHIM_PATH in sys.modules:
            return

    shim = types.ModuleType(_RAGAS_VERTEXAI_SHIM_PATH)

    class ChatVertexAI:  # pragma: no cover - compatibility shim only
        pass

    shim.ChatVertexAI = ChatVertexAI
    sys.modules[_RAGAS_VERTEXAI_SHIM_PATH] = shim


def _load_golden_set(path: Path) -> list[GoldenCase]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("queries", [])
    if not rows:
        raise ValueError("Golden set must contain at least one query")

    cases: list[GoldenCase] = []
    for row in rows:
        cases.append(
            GoldenCase(
                case_id=str(row["id"]),
                question=str(row["text"]),
                ground_truth=str(row["ground_truth"]),
            )
        )
    return cases


def _extract_answer(payload: dict[str, Any]) -> str:
    estimate = payload.get("generation", {}).get("estimate", {})
    answer = str(estimate.get("estimate_markdown") or estimate.get("summary") or "").strip()
    if not answer:
        return "No estimate generated."
    return answer


def _extract_contexts(payload: dict[str, Any]) -> list[str]:
    retrieval = payload.get("retrieval", {}).get("retrieval", {})
    chunks = retrieval.get("chunks", [])
    contexts = [str(chunk.get("content", "")).strip() for chunk in chunks if str(chunk.get("content", "")).strip()]
    if contexts:
        return contexts

    assembly_context = str(payload.get("assembly", {}).get("context_block", "")).strip()
    return [assembly_context] if assembly_context else []


def _compute_citation_stats(payload: dict[str, Any]) -> CitationStats:
    estimate = payload.get("generation", {}).get("estimate", {})
    line_items = estimate.get("line_items", [])
    retrieved_chunks = payload.get("retrieval", {}).get("retrieval", {}).get("chunks", [])
    valid_refs = {
        (str(chunk.get("chunk_id")), str(chunk.get("document_id")))
        for chunk in retrieved_chunks
    }

    grounded_line_items = 0
    ungrounded_line_items = 0
    dangling_source_refs = 0

    for line_item in line_items:
        if bool(line_item.get("grounded")):
            grounded_line_items += 1
        else:
            ungrounded_line_items += 1

        for source in line_item.get("sources", []):
            ref_key = (str(source.get("chunk_id")), str(source.get("document_id")))
            if ref_key not in valid_refs:
                dangling_source_refs += 1

    return CitationStats(
        grounded_line_items=grounded_line_items,
        ungrounded_line_items=ungrounded_line_items,
        dangling_source_refs=dangling_source_refs,
    )


def _build_ragas_metrics() -> list[Any]:
    _ensure_ragas_import_compat()
    from ragas.metrics import answer_relevancy, context_precision, context_recall, faithfulness

    return [faithfulness, answer_relevancy, context_precision, context_recall]


def _score_case(
    *,
    case_id: str,
    question: str,
    ground_truth: str,
    payload: dict[str, Any],
    judge_model: str,
    embedding_model: str,
) -> CaseResult:
    _ensure_ragas_import_compat()
    from datasets import Dataset
    from langchain_openai import ChatOpenAI, OpenAIEmbeddings
    from ragas import evaluate

    dataset = Dataset.from_dict(
        {
            "question": [question],
            "answer": [_extract_answer(payload)],
            "contexts": [_extract_contexts(payload)],
            "ground_truth": [ground_truth],
        }
    )
    llm = ChatOpenAI(model=judge_model, temperature=0)
    embeddings = OpenAIEmbeddings(model=embedding_model)
    metrics = _build_ragas_metrics()
    citation_stats = _compute_citation_stats(payload)

    scores_df = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    ).to_pandas()
    score_row = cast(dict[str, Any], scores_df.iloc[0].to_dict())

    return CaseResult(
        case_id=case_id,
        answer_relevancy=float(score_row["answer_relevancy"]),
        faithfulness=float(score_row["faithfulness"]),
        context_precision=float(score_row["context_precision"]),
        context_recall=float(score_row["context_recall"]),
        grounded_line_items=citation_stats.grounded_line_items,
        ungrounded_line_items=citation_stats.ungrounded_line_items,
        dangling_source_refs=citation_stats.dangling_source_refs,
    )


def _request_estimate(
    *,
    client: httpx.Client,
    base_url: str,
    transcript: str,
    top_k: int,
    mode: str,
    rerank: bool,
) -> dict[str, Any]:
    headers: dict[str, str] = {}
    if settings.internal_api_key:
        headers["X-Internal-API-Key"] = settings.internal_api_key

    response = client.post(
        f"{base_url.rstrip('/')}/api/v1/rag/estimate",
        json={
            "transcript": transcript,
            "top_k": top_k,
            "mode": mode,
            "rerank": rerank,
        },
        headers=headers,
    )
    response.raise_for_status()
    return response.json()


def _render_case_table(results: list[CaseResult]) -> str:
    header = (
        "| Case | Answer Relevancy | Faithfulness | Context Precision | "
        "Context Recall | RAGAS Mean | Grounded Lines | Ungrounded Lines | Dangling Refs |"
    )
    divider = "|---|---:|---:|---:|---:|---:|---:|---:|---:|"
    rows = [
        (
            f"| {result.case_id} | {result.answer_relevancy:.4f} | {result.faithfulness:.4f} | "
            f"{result.context_precision:.4f} | {result.context_recall:.4f} | {result.ragas_mean:.4f} | "
            f"{result.grounded_line_items} | {result.ungrounded_line_items} | {result.dangling_source_refs} |"
        )
        for result in results
    ]
    average_row = (
        f"| average | {mean(result.answer_relevancy for result in results):.4f} | "
        f"{mean(result.faithfulness for result in results):.4f} | "
        f"{mean(result.context_precision for result in results):.4f} | "
        f"{mean(result.context_recall for result in results):.4f} | "
        f"{mean(result.ragas_mean for result in results):.4f} | "
        f"{mean(result.grounded_line_items for result in results):.2f} | "
        f"{mean(result.ungrounded_line_items for result in results):.2f} | "
        f"{mean(result.dangling_source_refs for result in results):.2f} |"
    )
    return "\n".join([header, divider, *rows, average_row])


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAG estimate generation with RAGAS metrics.")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL for ai-engine API")
    parser.add_argument(
        "--golden-set",
        default="tests/evals/hybrid_rerank_golden_set.json",
        help="Path to the RAGAS golden set JSON relative to ai-engine root",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Top-k retrieved chunks to request")
    parser.add_argument(
        "--mode",
        choices=["vector", "hybrid"],
        default="hybrid",
        help="Retrieval mode for the evaluated pipeline",
    )
    parser.add_argument("--rerank", action="store_true", help="Enable reranking during retrieval")
    parser.add_argument(
        "--judge-model",
        default="gpt-4o-mini",
        help="OpenAI chat model used as RAGAS judge",
    )
    parser.add_argument(
        "--embedding-model",
        default="text-embedding-3-small",
        help="OpenAI embedding model for RAGAS metrics requiring embeddings",
    )
    parser.add_argument("--timeout-seconds", type=float, default=180.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    _require_eval_dependencies()
    _require_openai_api_key()

    golden_path = (ROOT / args.golden_set).resolve()
    if not golden_path.exists():
        raise FileNotFoundError(f"Golden set not found: {golden_path}")

    cases = _load_golden_set(golden_path)
    results: list[CaseResult] = []

    with httpx.Client(timeout=args.timeout_seconds) as client:
        for case in cases:
            payload = _request_estimate(
                client=client,
                base_url=args.base_url,
                transcript=case.question,
                top_k=args.top_k,
                mode=args.mode,
                rerank=args.rerank,
            )
            results.append(_score_case(
                case_id=case.case_id,
                question=case.question,
                ground_truth=case.ground_truth,
                payload=payload,
                judge_model=args.judge_model,
                embedding_model=args.embedding_model,
            ))

    print("# RAGAS Baseline")
    print()
    print(_render_case_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())