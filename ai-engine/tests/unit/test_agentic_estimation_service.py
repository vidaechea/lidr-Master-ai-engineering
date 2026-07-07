from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.service import AgenticEstimationService
from app.agents.tools import calculate_estimate, search_budgets
from app.domain.schemas.estimation import EstimationRequest
from app.generation.rag.schemas import RetrievalResult, RetrievedChunk


def _usage(input_tokens: int = 100, output_tokens: int = 50, reasoning_tokens: int = 0) -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning_tokens),
    )


def _reasoning_item(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="reasoning",
        summary=[SimpleNamespace(text=text)],
    )


def _function_call(name: str, call_id: str, arguments: dict[str, object]) -> SimpleNamespace:
    return SimpleNamespace(
        type="function_call",
        name=name,
        call_id=call_id,
        arguments=json.dumps(arguments),
    )


def _message(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        type="message",
        content=[SimpleNamespace(type="output_text", text=text)],
    )


class TestAgenticTools:
    async def test_search_budgets_falls_back_when_reranker_runtime_load_fails(self):
        retrieval = RetrievalResult(
            query="backend api",
            top_k=3,
            candidates_evaluated=1,
            low_confidence=False,
            chunks=[],
        )
        retriever = MagicMock()
        retriever.search_with_query = AsyncMock(
            side_effect=[RuntimeError("sentence-transformers is required for reranking"), retrieval]
        )

        results = await search_budgets(
            retriever,
            query="backend api",
            filters={
                "component_type": "backend",
                "client_sector": None,
                "date_range": None,
                "top_k": 3,
            },
        )

        assert results == []
        assert retriever.search_with_query.await_count == 2

    async def test_search_budgets_translates_retrieval_result(self):
        retrieval = RetrievalResult(
            query="backend api",
            top_k=3,
            candidates_evaluated=1,
            low_confidence=False,
            chunks=[
                RetrievedChunk(
                    source_id="src-1",
                    chunk_id=1,
                    document_id=10,
                    chunk_type="budget_component",
                    content=(
                        "[Project: Internal platform]\n"
                        "[Client sector: finance | Year: 2024 | Main tech: FastAPI]\n"
                        "\n"
                        "Component: Backend API\n"
                        "Description: Core business endpoints\n"
                        "Estimated hours: 48"
                    ),
                    distance=0.12,
                    metadata={
                        "budget_id": "budget-1",
                        "estimated_hours": 48,
                        "year": 2024,
                        "client_sector": "finance",
                        "main_technology": "FastAPI",
                    },
                )
            ],
        )
        retriever = MagicMock()
        retriever.search_with_query = AsyncMock(return_value=retrieval)

        results = await search_budgets(
            retriever,
            query="backend api",
            filters={
                "component_type": "backend",
                "client_sector": "finance",
                "date_range": {"from_year": 2023, "to_year": 2024},
                "top_k": 3,
            },
        )

        assert results[0]["component_name"] == "Backend API"
        assert results[0]["amount"] == 48.0
        retriever.search_with_query.assert_awaited_once()

    def test_calculate_estimate_uses_arithmetic_mean(self):
        result = calculate_estimate(
            [
                {"name": "Backend API", "reference_amounts": [40, 50, 60]},
                {"name": "Mobile app", "reference_amounts": [20, 30]},
            ]
        )

        assert result.total_amount == 75.0
        assert [component.estimated_amount for component in result.components] == [50.0, 25.0]


class TestAgenticEstimationService:
    async def test_estimate_runs_manual_tool_loop(self):
        transcript = "We need a backend API, an ERP integration, and a mobile app."
        request = EstimationRequest(transcription=transcript)

        search_call = _function_call(
            "search_budgets",
            "call-search-1",
            {"query": "backend API", "filters": {"component_type": "backend", "client_sector": None, "date_range": None, "top_k": 5}},
        )
        calculate_call = _function_call(
            "calculate_estimate",
            "call-calc-1",
            {
                "components": [
                    {"name": "Backend API", "reference_amounts": [40, 50]},
                    {"name": "ERP integration", "reference_amounts": [30, 35]},
                ]
            },
        )

        responses = [
            SimpleNamespace(
                id="resp-1",
                output=[_reasoning_item("Separate the request into backend, ERP, and mobile components."), search_call],
                output_text="",
                usage=_usage(120, 20, 15),
            ),
            SimpleNamespace(
                id="resp-2",
                output=[_reasoning_item("I have enough historical references for the first components."), calculate_call],
                output_text="",
                usage=_usage(80, 18, 12),
            ),
            SimpleNamespace(
                id="resp-3",
                output=[_reasoning_item("Return the consolidated estimate and summarize the result."), _message("Final estimate ready.")],
                output_text="Final estimate ready.",
                usage=_usage(60, 10, 6),
            ),
        ]

        retriever = MagicMock()
        retriever.search_with_query = AsyncMock(
            return_value=RetrievalResult(
                query="backend API",
                top_k=5,
                candidates_evaluated=1,
                low_confidence=False,
                chunks=[
                    RetrievedChunk(
                        source_id="src-1",
                        chunk_id=1,
                        document_id=10,
                        chunk_type="budget_component",
                        content="Component: Backend API\nEstimated hours: 48",
                        distance=0.1,
                        metadata={"budget_id": "budget-1", "estimated_hours": 48, "year": 2024},
                    )
                ],
            )
        )

        client = MagicMock()
        client.responses.create = MagicMock(side_effect=responses)

        with (
            patch("app.agents.service.check_input"),
            patch("app.agents.service._get_moderation_client", return_value=None),
        ):
            service = AgenticEstimationService(client=client, retriever=retriever)
            result = await service.estimate(request)

        assert result.response_id == "resp-3"
        assert result.structured_result.total_amount == 77.5
        assert len(result.trace) == 2
        assert "search_budgets" in result.trace[0].action
        assert "calculate_estimate" in result.trace[1].action
        assert result.estimation == "Final estimate ready."
