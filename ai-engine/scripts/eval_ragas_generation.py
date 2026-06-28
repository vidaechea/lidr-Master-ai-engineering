#!/usr/bin/env python3
"""Evaluate RAG estimate generation quality with the four RAGAS metrics.

The runner calls the full RAG estimation endpoint over HTTP, extracts the
generated estimate and retrieved contexts, and computes:

- answer relevancy
- faithfulness
- contextual precision
- contextual recall

It also reports citation integrity counters derived from line-level source
references so dangling citations become visible in the same report.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402


@dataclass(frozen=True)
class GoldenCase:
    case_id: str
    transcript: str
    reference_answer: str


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
    for module_name in ("ragas", "datasets"):
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    if missing:
        missing_csv = ", ".join(missing)
        raise SystemExit(
            "Missing evaluation dependencies: "
            f"{missing_csv}. Install them with `uv sync --extra evals` or "
            "`uv add --dev ragas datasets`."
        )


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
                transcript=str(row["transcript"]),
                reference_answer=str(row["reference_answer"]),
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


def _build_test_case(*, transcript: str, reference_answer: str, payload: dict[str, Any]):
    from deepeval.test_case import LLMTestCase

    return LLMTestCase(
        input=transcript,
        actual_output=_extract_answer(payload),
        expected_output=reference_answer,
        retrieval_context=_extract_contexts(payload),
    )


def _build_metrics(eval_model: str):
    from deepeval.metrics.ragas import (
        RAGASAnswerRelevancyMetric,
        RAGASContextualPrecisionMetric,
        RAGASContextualRecallMetric,
        RAGASFaithfulnessMetric,
    )

    return {
        "answer_relevancy": RAGASAnswerRelevancyMetric(threshold=0.0, model=eval_model),
        "faithfulness": RAGASFaithfulnessMetric(threshold=0.0, model=eval_model),
        "context_precision": RAGASContextualPrecisionMetric(threshold=0.0, model=eval_model),
        "context_recall": RAGASContextualRecallMetric(threshold=0.0, model=eval_model),
    }


def _score_case(*, transcript: str, reference_answer: str, payload: dict[str, Any], eval_model: str) -> CaseResult:
    test_case = _build_test_case(
        transcript=transcript,
        reference_answer=reference_answer,
        payload=payload,
    )
    metrics = _build_metrics(eval_model)
    citation_stats = _compute_citation_stats(payload)

    scores = {name: metric.measure(test_case) for name, metric in metrics.items()}

    return CaseResult(
        case_id="",
        answer_relevancy=float(scores["answer_relevancy"]),
        faithfulness=float(scores["faithfulness"]),
        context_precision=float(scores["context_precision"]),
        context_recall=float(scores["context_recall"]),
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
    return "\n".join([header, divider, *rows])


def _render_summary_table(results: list[CaseResult]) -> str:
    def _avg(selector: str) -> float:
        return mean(getattr(result, selector) for result in results)

    return "\n".join(
        [
            "| Metric | Mean |",
            "|---|---:|",
            f"| Answer Relevancy | {_avg('answer_relevancy'):.4f} |",
            f"| Faithfulness | {_avg('faithfulness'):.4f} |",
            f"| Context Precision | {_avg('context_precision'):.4f} |",
            f"| Context Recall | {_avg('context_recall'):.4f} |",
            f"| RAGAS Mean | {mean(result.ragas_mean for result in results):.4f} |",
            f"| Dangling Source Refs / Case | {_avg('dangling_source_refs'):.4f} |",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate RAG estimate generation with RAGAS metrics.")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Base URL for ai-engine API")
    parser.add_argument(
        "--golden-set",
        default="tests/evals/ragas_generation_golden_set.json",
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
        "--eval-model",
        default="gpt-4o-mini",
        help="Evaluation model used internally by the RAGAS wrappers",
    )
    parser.add_argument("--timeout-seconds", type=float, default=180.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    _require_eval_dependencies()

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
                transcript=case.transcript,
                top_k=args.top_k,
                mode=args.mode,
                rerank=args.rerank,
            )
            scored = _score_case(
                transcript=case.transcript,
                reference_answer=case.reference_answer,
                payload=payload,
                eval_model=args.eval_model,
            )
            results.append(
                CaseResult(
                    case_id=case.case_id,
                    answer_relevancy=scored.answer_relevancy,
                    faithfulness=scored.faithfulness,
                    context_precision=scored.context_precision,
                    context_recall=scored.context_recall,
                    grounded_line_items=scored.grounded_line_items,
                    ungrounded_line_items=scored.ungrounded_line_items,
                    dangling_source_refs=scored.dangling_source_refs,
                )
            )

    print("# RAGAS Summary")
    print()
    print(_render_summary_table(results))
    print()
    print("# Per-Case Results")
    print()
    print(_render_case_table(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())