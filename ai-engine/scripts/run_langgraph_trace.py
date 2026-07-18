from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.service import AgenticEstimationService
from app.domain.schemas.estimation import EstimationRequest
from app.generation.rag.schemas import RetrievalResult, RetrievedChunk


class DemoRetriever:
    async def search_with_query(self, query, k: int, mode: str | None = None, rerank: bool | None = None):
        await asyncio.sleep(0)
        _ = (mode, rerank)
        query_text = getattr(query, "search_text", str(query)).lower()
        if "mobile" in query_text:
            hours = 120
            name = "Mobile App"
        elif "erp" in query_text or "integrat" in query_text:
            hours = 95
            name = "ERP Integration"
        elif "frontend" in query_text or "web" in query_text:
            hours = 88
            name = "Frontend Web"
        elif "devops" in query_text or "deploy" in query_text:
            hours = 42
            name = "DevOps and Deployment"
        elif "qa" in query_text or "test" in query_text:
            hours = 56
            name = "QA and Testing"
        else:
            hours = 110
            name = "Backend API"

        return RetrievalResult(
            query=str(query_text),
            top_k=k,
            candidates_evaluated=1,
            low_confidence=False,
            chunks=[
                RetrievedChunk(
                    source_id="demo-source",
                    chunk_id=1,
                    document_id=1,
                    chunk_type="budget_component",
                    content=f"Component: {name}\nEstimated hours: {hours}",
                    distance=0.1,
                    metadata={
                        "budget_id": f"demo-{name.lower().replace(' ', '-')}",
                        "estimated_hours": hours,
                        "year": 2025,
                    },
                )
            ],
        )


async def main() -> None:
    fixture_path = Path("app/foundation/fixtures/sample_transcript_complex.txt")
    transcript = fixture_path.read_text(encoding="utf-8")

    checkpoint_dsn = os.getenv(
        "LANGGRAPH_CHECKPOINT_DSN",
        "postgresql://localhost:5432/estimator",
    )
    service = AgenticEstimationService(
        retriever=DemoRetriever(),
        checkpoint_dsn=checkpoint_dsn,
    )
    request = EstimationRequest(transcription=transcript)
    result = await service.estimate(request)

    print("=== LANGGRAPH TRACE EXECUTION ===")
    print(f"response_id: {result.response_id}")
    print(f"status: {result.structured_result.status}")
    print(f"total_amount: {result.structured_result.total_amount}")
    print("trace_steps:")
    print(json.dumps([step.model_dump() for step in result.trace], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
