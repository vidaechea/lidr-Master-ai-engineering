from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.domain.agent_estimation import agent_estimate_task_hours, agent_propose_structure
from app.domain.schemas.graph_estimation import ActivityEntry, GraphRunState, PendingGate
from app.generation.rag.schemas import EstimationQuery, TaskHoursModuleInput, TaskHoursTaskInput
from app.generation.rag.retriever_service import SemanticRetriever


class GraphRunError(Exception):
    """Domain error for graph run lifecycle operations."""


class GraphActivityLog:
    """In-memory per-run activity feed for live polling in development."""

    def __init__(self) -> None:
        self._entries: dict[str, list[dict[str, Any]]] = {}

    def reset(self, estimation_id: str) -> None:
        self._entries[estimation_id] = []

    def append(self, estimation_id: str, *, node: str, label: str, message: str) -> None:
        entries = self._entries.setdefault(estimation_id, [])
        entries.append(
            ActivityEntry(
                seq=len(entries) + 1,
                node=node,
                label=label,
                message=message,
                ts=datetime.now(timezone.utc).isoformat(),
            ).model_dump()
        )

    def read(self, estimation_id: str) -> list[dict[str, Any]]:
        return list(self._entries.get(estimation_id, []))


class GraphRunService:
    """Service-layer orchestration with two human gates and resumable state."""

    def __init__(self, *, retriever: SemanticRetriever, activity: GraphActivityLog) -> None:
        self._retriever = retriever
        self._activity = activity
        self._runs: dict[str, GraphRunState] = {}
        self._transcripts: dict[str, str] = {}

    def start(self, *, estimation_id: str, transcript: str) -> GraphRunState:
        self._activity.reset(estimation_id)
        self._transcripts[estimation_id] = transcript
        self._runs[estimation_id] = GraphRunState(estimation_id=estimation_id, state="running")
        self._activity.append(
            estimation_id,
            node="classifier",
            label="Classifier",
            message="Iniciando clasificación y reformulación del brief.",
        )

        query = EstimationQuery(
            search_text=transcript[:2_000],
            sector=None,
            year_from=None,
            year_to=None,
            chunk_types=["budget_component"],
            keywords=[],
        )
        structure = agent_propose_structure(
            query,
            model=settings.llm_model,
            reasoning_effort=settings.rag_pipeline_generation_reasoning_effort,
            persona=None,
        )
        complexity = self._compute_complexity(transcript)
        modules = [module.model_dump() for module in structure.estimate.modules]

        self._activity.append(
            estimation_id,
            node="structure",
            label="Structure",
            message=f"Estructura propuesta con {len(modules)} módulo(s).",
        )
        paused = GraphRunState(
            estimation_id=estimation_id,
            state="paused",
            complexity=complexity,
            structure={"modules": modules},
            pending_gate=PendingGate(
                gate="structure_review",
                estimation_id=estimation_id,
                payload={"complexity": complexity, "modules": modules},
            ),
        )
        self._runs[estimation_id] = paused
        self._activity.append(
            estimation_id,
            node="gate_structure",
            label="Gate 1",
            message="Pausado para revisión humana de la estructura.",
        )
        return paused

    async def resume(self, *, estimation_id: str, decision: dict[str, Any]) -> GraphRunState:
        state = self._runs.get(estimation_id)
        if state is None:
            raise GraphRunError("Unknown estimation_id.")
        if state.state != "paused" or state.pending_gate is None:
            raise GraphRunError("No pending human gate for this estimation_id.")

        if state.pending_gate.gate == "structure_review":
            return await self._resume_structure_gate(estimation_id=estimation_id, state=state, decision=decision)
        return self._resume_final_gate(estimation_id=estimation_id, state=state, decision=decision)

    def get_state(self, *, estimation_id: str) -> GraphRunState:
        state = self._runs.get(estimation_id)
        if state is None:
            raise GraphRunError("Unknown estimation_id.")
        return state

    def get_progress(self, *, estimation_id: str) -> dict[str, Any]:
        state = self.get_state(estimation_id=estimation_id)
        payload = state.model_dump()
        payload["activity"] = self._activity.read(estimation_id)
        return payload

    def record_error(self, *, estimation_id: str, message: str) -> None:
        state = self._runs.get(estimation_id)
        if state is None:
            return
        errors = [*state.errors, message]
        updated = state.model_copy(update={"state": "completed", "errors": errors, "status": "needs_review"})
        self._runs[estimation_id] = updated
        self._activity.append(estimation_id, node="error", label="Error", message=message)

    def build_proposal(self, *, estimation_id: str) -> dict[str, str]:
        state = self.get_state(estimation_id=estimation_id)
        if state.state != "completed" or state.estimate is None:
            raise GraphRunError("No completed estimate for this estimation_id.")

        if state.proposal:
            return {
                "estimation_id": estimation_id,
                "title": "Propuesta comercial",
                "body_markdown": state.proposal,
            }

        total_hours = int(state.estimate.get("total_hours") or 0)
        total_days = round(total_hours / 8, 1) if total_hours else 0.0
        proposal = (
            "## Propuesta comercial\n\n"
            f"- Estimación validada: **{total_hours} horas** (~{total_days} días).\n"
            "- Entrega propuesta en fases incrementales con hitos semanales.\n"
            "- Recomendación: comenzar con sprint de descubrimiento y backlog priorizado.\n"
        )
        completed = state.model_copy(update={"proposal": proposal})
        self._runs[estimation_id] = completed
        return {
            "estimation_id": estimation_id,
            "title": "Propuesta comercial",
            "body_markdown": proposal,
        }

    async def _resume_structure_gate(
        self,
        *,
        estimation_id: str,
        state: GraphRunState,
        decision: dict[str, Any],
    ) -> GraphRunState:
        modules_raw = decision.get("modules")
        if not isinstance(modules_raw, list) or not modules_raw:
            modules_raw = (state.structure or {}).get("modules") or []
        modules = self._to_task_hour_modules(modules_raw)
        if not modules:
            raise GraphRunError("Structure review must include at least one module with tasks.")

        self._activity.append(
            estimation_id,
            node="hours",
            label="Hours",
            message="Calculando horas por tarea con recuperación histórica.",
        )

        task_hours_result = await agent_estimate_task_hours(
            modules,
            retriever=self._retriever,
            top_k=settings.rag_pipeline_task_hours_top_k,
            distance_threshold=settings.rag_pipeline_task_hours_distance_threshold,
            contradiction_threshold=settings.rag_pipeline_task_hours_contradiction_threshold,
            model=settings.llm_model,
            reasoning_effort=settings.rag_pipeline_generation_reasoning_effort,
            max_iterations=2,
            persona=None,
        )

        task_hours = [item.model_dump() for item in task_hours_result.tasks]
        estimate = self._build_estimate(modules_raw, task_hours)
        analysis_report = self._build_analysis_report(task_hours)

        self._activity.append(
            estimation_id,
            node="analysis",
            label="Analysis",
            message="Informe de fiabilidad generado para revisión final.",
        )

        paused = GraphRunState(
            estimation_id=estimation_id,
            state="paused",
            complexity=state.complexity,
            structure={"modules": modules_raw},
            task_hours=task_hours,
            estimate=estimate,
            analysis_report=analysis_report,
            pending_gate=PendingGate(
                gate="final_review",
                estimation_id=estimation_id,
                payload={"estimate": estimate, "analysis_report": analysis_report},
            ),
        )
        self._runs[estimation_id] = paused
        self._activity.append(
            estimation_id,
            node="gate_final",
            label="Gate 2",
            message="Pausado para validación final humana.",
        )
        return paused

    def _resume_final_gate(
        self,
        *,
        estimation_id: str,
        state: GraphRunState,
        decision: dict[str, Any],
    ) -> GraphRunState:
        estimate = dict(state.estimate or {})
        overrides = decision.get("estimate_overrides")
        if isinstance(overrides, dict):
            modules_override = overrides.get("modules")
            if isinstance(modules_override, list):
                estimate["modules"] = modules_override
                estimate = self._recompute_totals(estimate)

        status = "validated" if bool(decision.get("validated", True)) else "needs_review"
        proposal = state.proposal
        if bool(decision.get("want_proposal")):
            proposal = self.build_proposal(estimation_id=estimation_id)["body_markdown"]

        completed = GraphRunState(
            estimation_id=estimation_id,
            state="completed",
            complexity=state.complexity,
            structure=state.structure,
            task_hours=state.task_hours,
            estimate=estimate,
            analysis_report=state.analysis_report,
            proposal=proposal,
            status=status,
            errors=state.errors,
        )
        self._runs[estimation_id] = completed
        self._activity.append(
            estimation_id,
            node="completed",
            label="Completed",
            message="Flujo agentico finalizado.",
        )
        return completed

    @staticmethod
    def _compute_complexity(transcript: str) -> str:
        size = len(transcript)
        if size < 1_000:
            return "low"
        if size < 5_000:
            return "medium"
        return "high"

    @staticmethod
    def _to_task_hour_modules(modules_raw: list[dict[str, Any]]) -> list[TaskHoursModuleInput]:
        modules: list[TaskHoursModuleInput] = []
        for module in modules_raw:
            name = str(module.get("name") or "").strip()
            if not name:
                continue
            tasks_raw = module.get("tasks") or []
            tasks: list[TaskHoursTaskInput] = []
            for task in tasks_raw:
                task_name = str(task.get("name") or "").strip()
                if not task_name:
                    continue
                tasks.append(
                    TaskHoursTaskInput(
                        name=task_name,
                        description=(task.get("description") or None),
                    )
                )
            if tasks:
                modules.append(TaskHoursModuleInput(name=name, tasks=tasks))
        return modules

    @staticmethod
    def _build_estimate(modules_raw: list[dict[str, Any]], task_hours: list[dict[str, Any]]) -> dict[str, Any]:
        by_key = {(item.get("module"), item.get("task")): item for item in task_hours}
        modules: list[dict[str, Any]] = []
        total_hours = 0.0
        for module in modules_raw:
            module_name = module.get("name")
            tasks_out: list[dict[str, Any]] = []
            for task in module.get("tasks") or []:
                key = (module_name, task.get("name"))
                hit = by_key.get(key, {})
                estimated_hours = hit.get("estimated_hours")
                estimated_hours = float(estimated_hours) if estimated_hours is not None else 0.0
                total_hours += estimated_hours
                tasks_out.append(
                    {
                        "name": task.get("name"),
                        "description": task.get("description"),
                        "estimated_hours": estimated_hours,
                        "reliability": hit.get("reliability"),
                        "has_match": bool(hit.get("has_match", False)),
                    }
                )
            modules.append({"name": module_name, "tasks": tasks_out})

        return {
            "modules": modules,
            "total_hours": round(total_hours, 2),
            "total_days": round(total_hours / 8.0, 2),
        }

    @staticmethod
    def _build_analysis_report(task_hours: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(task_hours)
        grounded = len([item for item in task_hours if item.get("has_match")])
        reliability_values = [float(item["reliability"]) for item in task_hours if item.get("reliability") is not None]
        avg_reliability = (sum(reliability_values) / len(reliability_values)) if reliability_values else 0.0
        return {
            "total_tasks": total,
            "grounded_tasks": grounded,
            "grounded_ratio": round((grounded / total), 4) if total else 0.0,
            "avg_reliability": round(avg_reliability, 4),
        }

    @staticmethod
    def _recompute_totals(estimate: dict[str, Any]) -> dict[str, Any]:
        modules = estimate.get("modules") or []
        total_hours = 0.0
        for module in modules:
            for task in module.get("tasks") or []:
                raw = task.get("estimated_hours")
                if raw is None:
                    continue
                try:
                    total_hours += float(raw)
                except (TypeError, ValueError):
                    continue
        estimate["total_hours"] = round(total_hours, 2)
        estimate["total_days"] = round(total_hours / 8.0, 2)
        return estimate
