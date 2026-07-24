from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4

import logfire
import structlog
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.agents.langgraph_flow import SequentialEstimationGraph
from app.agents.schemas import (
    AgentTraceStep,
    AgenticEstimate,
    AgenticEstimationResponse,
    AgenticPendingReview,
    AgenticRunState,
)
from app.config import settings
from app.dependencies import get_semantic_retriever
from app.domain.estimation_service import _get_moderation_client
from app.domain.schemas.estimation import EstimationRequest
from app.foundation.guardrails.input import check_input
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)
_THREAD_PREFIX = "s14"

_LOGFIRE_CONFIGURED = False


class AgenticRunNotFoundError(RuntimeError):
    pass


class AgenticRunNotPausedError(RuntimeError):
    pass


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
        self._checkpoint_schema_ready = False
        self._checkpoint_setup_lock = asyncio.Lock()
        _configure_logfire_once()

    async def warmup(self) -> None:
        """Prepare checkpoint schema once during app startup."""
        await self._ensure_checkpoint_schema()

    async def estimate(
        self,
        request: EstimationRequest,
        *,
        prompt_version: str = "v1",
        estimation_id: str | None = None,
    ) -> AgenticEstimationResponse:
        await asyncio.to_thread(
            check_input,
            request.transcription,
            openai_client=_get_moderation_client(),
        )
        effective_estimation_id = estimation_id or self._build_estimation_id(request)
        graph_state = await self._run_graph(request=request, estimation_id=effective_estimation_id)
        graph_state = await self._state_from_interrupt_if_needed(estimation_id=effective_estimation_id, graph_state=graph_state)
        if graph_state.get("__interrupt__"):
            graph_state = self._mark_awaiting_human_review(graph_state)
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
            estimation_id=effective_estimation_id,
        )

        return AgenticEstimationResponse(
            estimation=final_text,
            structured_result=structured_result,
            trace=trace_steps,
            model=request.model or self._model_name,
            response_id=effective_estimation_id,
            input_tokens=0,
            output_tokens=0,
            reasoning_tokens=0,
            prompt_version=prompt_version,
            reasoning_effort=self._reasoning_effort,  # type: ignore[arg-type]
        )

    async def get_state(self, *, estimation_id: str) -> AgenticRunState:
        if not self._use_postgres_checkpointer:
            return AgenticRunState(
                estimation_id=estimation_id,
                state="missing",
                status="missing",
            )

        config = {"configurable": {"thread_id": self._thread_id(estimation_id)}}
        await self._ensure_checkpoint_schema()
        async with AsyncPostgresSaver.from_conn_string(self._checkpoint_dsn) as saver:
            graph = self._graph_flow.build(checkpointer=saver)
            snapshot = await graph.aget_state(config)

        values = dict(getattr(snapshot, "values", {}) or {})
        if not values and not getattr(snapshot, "created_at", None):
            return AgenticRunState(
                estimation_id=estimation_id,
                state="missing",
                status="missing",
            )

        pending_review = self._pending_review_from_snapshot(estimation_id=estimation_id, snapshot=snapshot)
        status = "awaiting_human_review" if pending_review else str(values.get("status") or "needs_review")
        estimate_payload = values.get("structured_estimate")

        return AgenticRunState(
            estimation_id=estimation_id,
            state="paused" if pending_review else "completed",
            status=status,
            pending_review=pending_review,
            structured_estimate=AgenticEstimate.model_validate(estimate_payload) if isinstance(estimate_payload, dict) else None,
            confidence=values.get("confidence"),
            validation=values.get("validation"),
            human_decision=values.get("human_decision"),
            routing_history=list(values.get("routing_history") or []),
            agent_contributions=list(values.get("agent_contributions") or []),
        )

    async def resume(
        self,
        *,
        estimation_id: str,
        decision: dict[str, object],
        prompt_version: str = "v1",
    ) -> AgenticEstimationResponse:
        graph_state = await self._resume_graph(estimation_id=estimation_id, decision=decision)
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

        return AgenticEstimationResponse(
            estimation=final_text,
            structured_result=structured_result,
            trace=trace_steps,
            model=self._model_name,
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
            "routing_history": [],
            "agent_contributions": [],
            "supervisor_steps": 0,
        }
        config = {"configurable": {"thread_id": self._thread_id(estimation_id)}}

        if self._use_postgres_checkpointer:
            await self._ensure_checkpoint_schema()
            async with AsyncPostgresSaver.from_conn_string(self._checkpoint_dsn) as saver:
                graph = self._graph_flow.build(checkpointer=saver)
                result = await graph.ainvoke(initial_state, config=config)
                return dict(result)

        graph = self._graph_flow.build(checkpointer=None)
        result = await graph.ainvoke(initial_state, config=config)
        return dict(result)

    async def _resume_graph(self, *, estimation_id: str, decision: dict[str, object]) -> dict[str, object]:
        config = {"configurable": {"thread_id": self._thread_id(estimation_id)}}

        if self._use_postgres_checkpointer:
            await self._ensure_checkpoint_schema()
            async with AsyncPostgresSaver.from_conn_string(self._checkpoint_dsn) as saver:
                graph = self._graph_flow.build(checkpointer=saver)
                snapshot = await graph.aget_state(config)
                if not (getattr(snapshot, "values", None) or getattr(snapshot, "created_at", None)):
                    raise AgenticRunNotFoundError(f"Unknown estimation_id: {estimation_id}")
                if not getattr(snapshot, "next", None):
                    raise AgenticRunNotPausedError(
                        f"No pending human review for estimation_id={estimation_id}"
                    )
                result = await graph.ainvoke(Command(resume=decision), config=config)
                return dict(result)

        graph = self._graph_flow.build(checkpointer=None)
        result = await graph.ainvoke(Command(resume=decision), config=config)
        return dict(result)

    async def _state_from_interrupt_if_needed(
        self,
        *,
        estimation_id: str,
        graph_state: dict[str, object],
    ) -> dict[str, object]:
        if "__interrupt__" not in graph_state:
            return graph_state
        if not self._use_postgres_checkpointer:
            return graph_state

        config = {"configurable": {"thread_id": self._thread_id(estimation_id)}}
        await self._ensure_checkpoint_schema()
        async with AsyncPostgresSaver.from_conn_string(self._checkpoint_dsn) as saver:
            graph = self._graph_flow.build(checkpointer=saver)
            snapshot = await graph.aget_state(config)
            values = dict(getattr(snapshot, "values", {}) or {})
            values["__interrupt__"] = graph_state["__interrupt__"]
            return values

    async def _ensure_checkpoint_schema(self) -> None:
        if not self._use_postgres_checkpointer:
            return
        if self._checkpoint_schema_ready:
            return
        async with self._checkpoint_setup_lock:
            if self._checkpoint_schema_ready:
                return
            async with AsyncPostgresSaver.from_conn_string(self._checkpoint_dsn) as saver:
                await saver.setup()
            self._checkpoint_schema_ready = True

    @staticmethod
    def _thread_id(estimation_id: str) -> str:
        return f"{_THREAD_PREFIX}:{estimation_id}"

    @staticmethod
    def _pending_review_from_snapshot(*, estimation_id: str, snapshot: object) -> AgenticPendingReview | None:
        paused = bool(getattr(snapshot, "next", None))
        interrupts = getattr(snapshot, "interrupts", None) or ()
        if not paused or not interrupts:
            return None
        payload = interrupts[0].value or {}
        return AgenticPendingReview(
            gate=str(payload.get("reason") or "low_confidence_review"),
            estimation_id=estimation_id,
            reasons=list(payload.get("reasons") or []),
            confidence=payload.get("confidence"),
            threshold=payload.get("threshold"),
            estimate=payload.get("estimate"),
            validation=payload.get("validation"),
        )

    @staticmethod
    def _mark_awaiting_human_review(graph_state: dict[str, object]) -> dict[str, object]:
        estimate_payload = dict(graph_state.get("structured_estimate", {}))
        if not estimate_payload:
            return graph_state
        estimate = AgenticEstimate.model_validate(estimate_payload)
        awaiting = estimate.model_copy(update={"status": "awaiting_human_review"})
        graph_state["structured_estimate"] = awaiting.model_dump()
        graph_state["status"] = "awaiting_human_review"
        graph_state["final_text"] = AgenticEstimationService._render_final_text(awaiting)
        return graph_state

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
        if result.confidence is not None:
            lines.append(f"Confidence: {result.confidence:.2f}")
        lines.append(f"Status: {result.status}")
        return "\n".join(lines)
