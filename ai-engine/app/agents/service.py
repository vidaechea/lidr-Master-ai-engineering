from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4

import logfire
import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.agents.langgraph_flow import SequentialEstimationGraph
from app.agents.schemas import AgentTraceStep, AgenticEstimate, AgenticEstimationResponse
from app.config import settings
from app.dependencies import get_semantic_retriever
from app.domain.estimation_service import _get_moderation_client
from app.domain.schemas.estimation import EstimationRequest
from app.foundation.guardrails.input import check_input
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)

_LOGFIRE_CONFIGURED = False

def _configure_logfire_once() -> None:
    global _LOGFIRE_CONFIGURED
    if _LOGFIRE_CONFIGURED:
        return
    try:
        logfire.configure(
            service_name="ai-engine-agentic-langgraph",
            environment=settings.app_env,
            send_to_logfire="if-token-present",
        )
    except Exception as exc:
        log.warning("logfire_config_failed", error=str(exc)[:400])
    _LOGFIRE_CONFIGURED = True


def _normalize_checkpoint_dsn(database_url: str) -> str:
    return (
        database_url
        .replace("postgresql+psycopg://", "postgresql://", 1)
        .replace("postgresql+asyncpg://", "postgresql://", 1)
    )


class AgenticEstimationService:
    def __init__(
        self,
        *,
        retriever: SemanticRetriever | None = None,
        model_name: str = "gpt-5",
        reasoning_effort: str = "medium",
        checkpoint_dsn: str | None = None,
        use_postgres_checkpointer: bool = True,
    ) -> None:
        self._retriever = retriever or get_semantic_retriever()
        self._graph_flow = SequentialEstimationGraph(retriever=self._retriever)
        self._model_name = model_name
        self._reasoning_effort = reasoning_effort
        self._checkpoint_dsn = _normalize_checkpoint_dsn(checkpoint_dsn or settings.database_url)
        self._use_postgres_checkpointer = use_postgres_checkpointer
        _configure_logfire_once()

    async def estimate(
        self,
        request: EstimationRequest,
        *,
        prompt_version: str = "v1",
    ) -> AgenticEstimationResponse:
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        estimation_id = self._build_estimation_id(request)
        graph_state = await self._run_graph(request=request, estimation_id=estimation_id)
        structured_result = AgenticEstimate.model_validate(graph_state["structured_estimate"])
        final_text = str(graph_state.get("final_text") or self._render_final_text(structured_result))
        trace_payload = graph_state.get("trace", [])
        trace_steps = [
            AgentTraceStep(
                step=idx,
                reasoning=step.get("reasoning", ""),
                action=step.get("action", ""),
                observation=step.get("observation", ""),
            )
            for idx, step in enumerate(trace_payload, start=1)
        ]

        log.info(
            "agentic_estimation_completed",
            model=request.model or self._model_name,
            prompt_version=prompt_version,
            steps=len(trace_steps),
            status=structured_result.status,
            estimation_id=estimation_id,
        )

        return AgenticEstimationResponse(
            estimation=final_text,
            structured_result=structured_result,
            trace=trace_steps,
            model=request.model or self._model_name,
            response_id=estimation_id,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            prompt_version=prompt_version,
            reasoning_effort=self._reasoning_effort,  # type: ignore[arg-type]
        )

    async def _run_graph(self, *, request: EstimationRequest, estimation_id: str) -> dict[str, object]:
        initial_state: dict[str, object] = {
            "estimation_id": estimation_id,
            "transcription": request.transcription,
            "budget_hits": [],
            "trace": [],
            "validation_errors": [],
        }
        config = {"configurable": {"thread_id": estimation_id}}

        if self._use_postgres_checkpointer:
            async with AsyncPostgresSaver.from_conn_string(self._checkpoint_dsn) as saver:
                await saver.setup()
                graph = self._graph_flow.build(checkpointer=saver)
                result = await graph.ainvoke(initial_state, config=config)
                return dict(result)

        graph = self._graph_flow.build(checkpointer=None)
        result = await graph.ainvoke(initial_state, config=config)
        return dict(result)

    @staticmethod
    def _build_estimation_id(request: EstimationRequest) -> str:
        digest = hashlib.sha256(request.transcription.encode("utf-8")).hexdigest()[:16]
        return f"estimate-{digest}-{uuid4().hex[:8]}"

    @staticmethod
    def _render_final_text(result: AgenticEstimate) -> str:
        lines = ["# Agentic estimate", ""]
        for component in result.components:
            lines.append(
                f"- {component.name}: {component.estimated_amount} {result.unit} "
                f"from {component.reference_count} references"
            )
        lines.append("")
        lines.append(f"Total: {result.total_amount} {result.unit}")
        lines.append(f"Status: {result.status}")
        return "\n".join(lines)
