"""Integration tests for RAG pipeline."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from starlette.requests import Request

from app.generation.rag.retriever_service import SemanticRetriever
from app.generation.rag.schemas import (
    AssembleStageResponse,
    EstimationQuery,
    FullEstimateRequest,
    GenerateStageResponse,
    RagPipelineEstimate,
    ReformulateStageResponse,
    ReformulateStageRequest,
    RetrievalResult,
    RetrieveStageResponse,
    RetrieveStageRequest,
    AssembleStageRequest,
    GenerateStageRequest,
)


@pytest.fixture
def mock_retriever():
    """Fixture for mocked semantic retriever."""
    retriever = AsyncMock(spec=SemanticRetriever)
    return retriever


@pytest.fixture
def mock_estimation_service():
    """Fixture for mocked estimation service."""
    service = AsyncMock()
    service.estimate = AsyncMock()
    return service


class TestRagPipelineIntegration:
    """Integration tests for RAG pipeline stages."""

    @pytest.mark.asyncio
    async def test_retrieval_with_filters(self, mock_retriever):
        """Test retrieval stage with metadata filters."""
        from app.generation.rag.schemas import (
            RetrievedChunk,
            RetrievalResult,
        )

        # Mock retriever response
        mock_result = RetrievalResult(
            query="test query",
            top_k=5,
            candidates_evaluated=20,
            low_confidence=False,
            chunks=[
                RetrievedChunk(
                    source_id="src-1",
                    chunk_id=1,
                    document_id=1,
                    chunk_type="budget_component",
                    content="Sample content",
                    distance=0.1,
                    metadata={"year": "2023"},
                )
            ],
        )

        mock_retriever.search_with_query = AsyncMock(return_value=mock_result)

        # Execute retrieval
        query = EstimationQuery(
            search_text="test query",
            sector="fintech",
            year_from=2023,
            year_to=2024,
            chunk_types=["budget_component"],
            keywords=["test"],
        )

        result = await mock_retriever.search_with_query(
            query=query,
            k=5,
            distance_threshold=0.35,
        )

        assert result.query == "test query"
        assert len(result.chunks) == 1
        assert result.candidates_evaluated == 20
        assert result.low_confidence is False

    def test_assembly_with_token_budget(self):
        """Test context assembly respects token budget."""
        from app.generation.rag.schemas import (
            RetrievedChunk,
            RetrievalResult,
        )

        # Simulate retrieved chunks
        chunks = [
            RetrievedChunk(
                source_id=f"src-{i}",
                chunk_id=i,
                document_id=1,
                chunk_type="budget_component",
                content="x" * 1000,  # ~250 tokens per chunk
                distance=0.1 * i,
                metadata={"year": "2023"},
            )
            for i in range(1, 6)
        ]

        retrieval = RetrievalResult(
            query="test",
            top_k=5,
            candidates_evaluated=10,
            low_confidence=False,
            chunks=chunks,
        )

        # Assemble with budget of 500 tokens (should include ~2 chunks)
        max_tokens = 500
        selected_texts = []
        selected_source_ids = []
        running_tokens = 0

        for chunk in retrieval.chunks:
            token_estimate = max(1, len(chunk.content) // 4)
            if running_tokens + token_estimate > max_tokens:
                break
            selected_texts.append(f"[{chunk.source_id}] {chunk.content}")
            selected_source_ids.append(chunk.source_id)
            running_tokens += token_estimate

        assert running_tokens <= max_tokens
        assert len(selected_source_ids) > 0
        # Should not include all chunks
        assert len(selected_source_ids) < len(chunks)

    def test_estimate_end_to_end_flow(self):
        """Test end-to-end estimate flow structure."""
        from app.generation.rag.schemas import (
            EstimateModule,
            EstimateTask,
            RagPipelineEstimate,
            FullEstimateResponse,
        )

        # Build estimate response
        estimate = RagPipelineEstimate(
            summary="Estimate summary",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module 1",
                    engineer_days=5.0,
                    tasks=[
                        EstimateTask(name="Task 1", engineer_days=3.0),
                        EstimateTask(name="Task 2", engineer_days=2.0),
                    ],
                )
            ],
            assumptions=["Assumption 1"],
            sources=["src-1", "src-2"],
        )

        # Build full response
        response = FullEstimateResponse(
            request_id="req-123",
            reformulation=MagicMock(),
            retrieval=MagicMock(),
            assembly=MagicMock(),
            generation=MagicMock(estimate=estimate),
            idempotency_hit=False,
        )

        assert response.generation.estimate.summary == "Estimate summary"
        assert len(response.generation.estimate.modules) == 1
        assert response.generation.estimate.modules[0].engineer_days == 5.0

    def test_reformulation_stage_structure(self):
        """Test reformulation stage produces correct structure."""
        from app.generation.rag.schemas import ReformulateStageResponse

        query = EstimationQuery(
            search_text="test query",
            sector=None,
            year_from=None,
            year_to=None,
            chunk_types=["budget_component"],
            keywords=["test"],
        )

        response = ReformulateStageResponse(
            query=query,
            used_fallback=False,
        )

        assert response.query.search_text == "test query"
        assert response.used_fallback is False
        assert len(response.query.keywords) > 0

    def test_retrieval_stage_low_confidence_detection(self):
        """Test low confidence detection in retrieval."""
        from app.generation.rag.schemas import (
            RetrievedChunk,
            RetrievalResult,
        )

        # High distance chunks (low confidence)
        chunks = [
            RetrievedChunk(
                source_id=f"src-{i}",
                chunk_id=i,
                document_id=1,
                chunk_type="budget_component",
                content="Content",
                distance=0.85,  # High distance
                metadata={"year": "2023"},
            )
            for i in range(1, 3)
        ]

        retrieval = RetrievalResult(
            query="test",
            top_k=5,
            candidates_evaluated=10,
            low_confidence=True,  # Detected as low confidence
            chunks=chunks,
        )

        assert retrieval.low_confidence is True
        assert all(chunk.distance > 0.8 for chunk in retrieval.chunks)

    def test_citation_validation_flow(self):
        """Test citation validation in estimate."""
        from app.generation.rag.schemas import (
            EstimateModule,
            EstimateTask,
            RagPipelineEstimate,
            RetrievedChunk,
        )
        from app.generation.rag.citation_validator_service import CitationValidatorService

        # Estimate referencing sources
        estimate = RagPipelineEstimate(
            summary="Based on [src-1] and [src-2]",
            low_confidence=False,
            modules=[
                EstimateModule(
                    name="Module",
                    engineer_days=5.0,
                    tasks=[EstimateTask(name="Task", engineer_days=5.0)],
                )
            ],
            assumptions=["Derived from src-1"],
            sources=["src-1", "src-2"],
        )

        # Retrieved chunks
        chunks = [
            RetrievedChunk(
                source_id="src-1",
                chunk_id=1,
                document_id=1,
                chunk_type="budget_component",
                content="Content 1",
                distance=0.1,
                metadata={"year": "2023"},
            ),
            RetrievedChunk(
                source_id="src-2",
                chunk_id=2,
                document_id=1,
                chunk_type="budget_component",
                content="Content 2",
                distance=0.2,
                metadata={"year": "2023"},
            ),
        ]

        validator = CitationValidatorService()
        validated, warnings = validator.validate_citations(estimate, chunks)

        assert len(warnings) == 0
        assert validated.sources == ["src-1", "src-2"]

    @pytest.mark.asyncio
    async def test_full_pipeline_uses_fallback_context_when_retrieval_is_empty(self, monkeypatch):
        """Full pipeline should not fail when no chunks are retrieved."""
        from app.api import rag_pipeline

        query = EstimationQuery(
            search_text="admin portal effort",
            sector="saas",
            year_from=None,
            year_to=None,
            chunk_types=["budget_component"],
            keywords=["admin", "portal"],
        )

        monkeypatch.setattr(
            rag_pipeline,
            "_reformulate",
            lambda transcript: ReformulateStageResponse(query=query, used_fallback=False),
        )

        async def _fake_retrieve(*, payload, retriever):
            await asyncio.sleep(0)
            return RetrieveStageResponse(
                retrieval=RetrievalResult(
                    query=payload.query.search_text,
                    top_k=payload.top_k or 5,
                    candidates_evaluated=0,
                    low_confidence=True,
                    chunks=[],
                )
            )

        monkeypatch.setattr(rag_pipeline, "_retrieve", _fake_retrieve)
        monkeypatch.setattr(
            rag_pipeline,
            "_assemble",
            lambda payload: AssembleStageResponse(
                context_block="",
                included_source_ids=[],
                token_count_estimate=0,
                truncated=False,
            ),
        )

        captured: dict[str, object] = {}

        async def _fake_generate(*, payload, tier, low_confidence, retrieved_chunks=None, max_retries=2):
            await asyncio.sleep(0)
            captured["context_block"] = payload.context_block
            captured["low_confidence"] = low_confidence
            return GenerateStageResponse(
                estimate=RagPipelineEstimate(
                    summary="Fallback response",
                    low_confidence=low_confidence,
                    modules=[],
                    assumptions=[],
                    sources=payload.source_ids,
                )
            )

        monkeypatch.setattr(rag_pipeline, "_generate", _fake_generate)

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/rag/estimate",
                "headers": [],
            }
        )

        response = await rag_pipeline.estimate_from_transcript(
            payload=FullEstimateRequest(transcript="Need estimate for an admin portal migration"),
            request=request,
            tier="developer",
            retriever=MagicMock(spec=SemanticRetriever),
            _="ok",
        )

        assert captured["context_block"] == "No retrieved context available."
        assert captured["low_confidence"] is True
        assert response.generation.estimate.low_confidence is True
