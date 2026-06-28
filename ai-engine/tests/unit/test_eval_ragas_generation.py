"""Tests for the RAGAS generation evaluation helpers."""

from __future__ import annotations

import json

from scripts.eval_ragas_generation import (
    _compute_citation_stats,
    _extract_answer,
    _extract_contexts,
    _load_golden_set,
)


def test_load_golden_set_reads_reference_answers(tmp_path):
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "id": "case-1",
                        "transcript": "Transcript",
                        "reference_answer": "Reference answer",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = _load_golden_set(golden_path)

    assert len(cases) == 1
    assert cases[0].case_id == "case-1"
    assert cases[0].reference_answer == "Reference answer"


def test_extract_answer_prefers_markdown_over_summary():
    payload = {
        "generation": {
            "estimate": {
                "estimate_markdown": "# Estimate\nDetailed output",
                "summary": "Short summary",
            }
        }
    }

    assert _extract_answer(payload) == "# Estimate\nDetailed output"


def test_extract_contexts_uses_retrieval_chunks_before_assembly_context():
    payload = {
        "retrieval": {
            "retrieval": {
                "chunks": [
                    {"content": "First chunk"},
                    {"content": "Second chunk"},
                ]
            }
        },
        "assembly": {"context_block": "Fallback context"},
    }

    assert _extract_contexts(payload) == ["First chunk", "Second chunk"]


def test_compute_citation_stats_counts_dangling_references():
    payload = {
        "retrieval": {
            "retrieval": {
                "chunks": [
                    {"chunk_id": 1, "document_id": 10},
                ]
            }
        },
        "generation": {
            "estimate": {
                "line_items": [
                    {
                        "grounded": True,
                        "sources": [
                            {"chunk_id": "1", "document_id": "10"},
                            {"chunk_id": "99", "document_id": "10"},
                        ],
                    },
                    {
                        "grounded": False,
                        "sources": [],
                    },
                ]
            }
        },
    }

    stats = _compute_citation_stats(payload)

    assert stats.grounded_line_items == 1
    assert stats.ungrounded_line_items == 1
    assert stats.dangling_source_refs == 1