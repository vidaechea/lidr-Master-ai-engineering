from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from app.agents.service import AgenticEstimationService
from app.agents.tools import calculate_estimate, search_budgets, validate_estimate
from app.domain.schemas.estimation import EstimationRequest
from app.generation.rag.schemas import RetrievalResult, RetrievedChunk


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

    def test_validate_estimate_reports_confidence_and_missing_references(self):
        estimate = calculate_estimate(
            [
                {"name": "Backend API", "reference_amounts": [40, 50]},
                {"name": "ERP Integration", "reference_amounts": []},
            ]
        )

        validation = validate_estimate(estimate)

        assert validation["confidence"] == 0.5
        assert validation["missing_reference_components"] == ["ERP Integration"]
        assert validation["no_historical_precedent"] is False


class TestAgenticEstimationService:
    async def test_estimate_runs_supervisor_multi_agent_langgraph(self):
        transcript = "We need a backend API, an ERP integration, and a mobile app."
        request = EstimationRequest(transcription=transcript)

        retriever = MagicMock()
        retriever.search_with_query = AsyncMock(
            return_value=RetrievalResult(
                query="Backend API",
                top_k=5,
                candidates_evaluated=1,
                low_confidence=False,
                chunks=[
                    RetrievedChunk(
                        source_id="src-1",
                        chunk_id=1,
                        document_id=10,
                        chunk_type="budget_component",
                        content="Component: Backend API\nEstimated hours: 50",
                        distance=0.1,
                        metadata={"budget_id": "budget-1", "estimated_hours": 50, "year": 2024},
                    )
                ],
            )
        )

        with (
            patch("app.agents.service.check_input"),
            patch("app.agents.service._get_moderation_client", return_value=None),
        ):
            service = AgenticEstimationService(
                retriever=retriever,
                use_postgres_checkpointer=False,
            )
            result = await service.estimate(request)

        assert result.response_id.startswith("estimate-")
        assert result.structured_result.total_amount > 0
        assert result.structured_result.status in {"validated", "needs_review", "awaiting_human_review"}
        assert result.structured_result.confidence is not None
        assert len(result.trace) >= 9
        assert "supervisor.route.requirements_extractor" in result.trace[0].action
        assert any("budget_searcher.search_budgets" in step.action for step in result.trace)
        assert any("coherence_validator.validate_estimate" in step.action for step in result.trace)
        assert "finalize" in result.trace[-1].action
        assert "Status:" in result.estimation

    async def test_estimate_pauses_for_human_review_when_confidence_is_low(self):
        transcript = "We need a backend API and an ERP integration for finance workflows."
        request = EstimationRequest(transcription=transcript)

        retriever = MagicMock()
        retriever.search_with_query = AsyncMock(
            return_value=RetrievalResult(
                query="Backend API",
                top_k=5,
                candidates_evaluated=0,
                low_confidence=True,
                chunks=[],
            )
        )

        with (
            patch("app.agents.service.check_input"),
            patch("app.agents.service._get_moderation_client", return_value=None),
        ):
            service = AgenticEstimationService(
                retriever=retriever,
                use_postgres_checkpointer=False,
            )
            result = await service.estimate(request)

        assert result.structured_result.status == "awaiting_human_review"
        assert result.structured_result.confidence == 0.0
        assert result.structured_result.validation["no_historical_precedent"] is True
        assert "Status: awaiting_human_review" in result.estimation
