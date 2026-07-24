from __future__ import annotations

import hashlib
import json
import re
from time import perf_counter
from typing import Any, Literal

import logfire
import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.schemas import AgenticEstimate, SupervisorRoutingDecision
from app.agents.supervisor import (
    SUPERVISOR_SYSTEM_PROMPT,
    build_route_audit_update,
    build_finalize_update_payload,
    build_human_decision_update,
    build_human_review_interrupt_payload,
    fallback_next,
    is_legal,
    requires_human_review,
    route_target_for_finish,
    summarize_state_for_router,
    validate_action,
)
from app.agents.supervisor.state import ComponentSpec, EstimationGraphState
from app.agents.tools import calculate_estimate, search_budgets, validate_estimate
from app.config import settings
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)

MOBILE_COMPONENT = "Mobile App"
GENERAL_SCOPE_COMPONENT = "General Scope"

AgentNode = Literal[
    "requirements_extractor",
    "budget_searcher",
    "estimate_generator",
    "coherence_validator",
    "human_review_gate",
    "finalize",
]


class SequentialEstimationGraph:
    def __init__(self, *, retriever: SemanticRetriever) -> None:
        self._retriever = retriever

    def build(self, *, checkpointer: Any | None = None):
        graph_builder = StateGraph(EstimationGraphState)

        graph_builder.add_node("supervisor", self.supervisor)
        graph_builder.add_node("requirements_extractor", self.requirements_extractor)
        graph_builder.add_node("budget_searcher", self.budget_searcher)
        graph_builder.add_node("estimate_generator", self.estimate_generator)
        graph_builder.add_node("coherence_validator", self.coherence_validator)
        graph_builder.add_node("human_review_gate", self.human_review_gate)
        graph_builder.add_node("finalize", self.finalize)

        graph_builder.add_edge(START, "supervisor")
        graph_builder.add_edge("requirements_extractor", "supervisor")
        graph_builder.add_edge("budget_searcher", "supervisor")
        graph_builder.add_edge("estimate_generator", "supervisor")
        graph_builder.add_edge("coherence_validator", "supervisor")
        graph_builder.add_edge("finalize", END)

        return graph_builder.compile(checkpointer=checkpointer)

    async def supervisor(self, state: EstimationGraphState) -> Command[AgentNode]:
        step = int(state.get("supervisor_steps") or 0)
        if step >= settings.agentic_supervisor_max_steps:
            return self._route_with_audit(
                goto="finalize",
                reason=f"Step budget {settings.agentic_supervisor_max_steps} exhausted.",
                step=step,
                source="limit",
                confidence=None,
            )

        target = fallback_next(state)
        reason = "Deterministic fallback based on unmet dependencies."
        source: Literal["llm", "fallback", "limit"] = "fallback"
        decision_confidence: Literal["low", "medium", "high"] | None = None

        try:
            decision = await self._route_with_model(state)
            if is_legal(decision.next_agent, state):
                target = decision.next_agent
                reason = decision.reason
                decision_confidence = decision.confidence
                source = "llm"
            else:
                reason = (
                    f"Router suggested illegal destination {decision.next_agent!r}. "
                    f"Using fallback {target!r}."
                )
        except Exception as exc:
            reason = f"Router unavailable ({type(exc).__name__}). Using deterministic fallback."
            log.warning("supervisor_router_failed", error=str(exc)[:300])

        if target == "finish":
            goto = route_target_for_finish(state)
            final_reason = reason if goto == "finalize" else "Ready to finish; routing through human review gate."
            return self._route_with_audit(
                goto=goto,
                reason=final_reason,
                step=step,
                source=source,
                confidence=decision_confidence,
            )

        return self._route_with_audit(
            goto=target,
            reason=reason,
            step=step,
            source=source,
            confidence=decision_confidence,
        )

    def requirements_extractor(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        transcription = state["transcription"]

        with logfire.span("agentic.langgraph.requirements_extractor", estimation_id=estimation_id):
            started = perf_counter()
            raw_chunks = re.split(r"[\n\r\.\!\?;]+", transcription)
            requirements = [chunk.strip() for chunk in raw_chunks if len(chunk.strip()) >= 15]
            if not requirements:
                requirements = [transcription.strip()[:240]]

            components = self._classify_components(requirements)
            return {
                "requirements": requirements,
                "components": components,
                "agent_contributions": [
                    {
                        "step": int(state.get("supervisor_steps") or 1),
                        "agent": "requirements_extractor",
                        "action": "extract_requirements",
                        "tool": None,
                        "outcome": "ok",
                        "summary": f"Extracted {len(requirements)} requirements and {len(components)} components.",
                        "args_digest": self._digest_payload({"transcript_len": len(transcription)}),
                        "duration_ms": int((perf_counter() - started) * 1000),
                    }
                ],
                "trace": [
                    {
                        "reasoning": "The requirements extractor has no business tools and only structures transcript facts.",
                        "action": "requirements_extractor",
                        "observation": f"Extracted {len(requirements)} requirements and classified {len(components)} components.",
                    }
                ],
            }

    async def budget_searcher(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        components = state.get("components", [])

        with logfire.span("agentic.langgraph.budget_searcher", estimation_id=estimation_id):
            allowed, denied_contribution = validate_action(
                agent="budget_searcher",
                tool="search_budgets",
                step=int(state.get("supervisor_steps") or 0),
            )
            if not allowed:
                return {
                    "agent_contributions": [denied_contribution],
                    "validation_errors": [denied_contribution["summary"]],
                }
            started = perf_counter()
            all_hits: list[dict[str, object]] = []
            component_hits: dict[str, list[dict[str, object]]] = {}

            for component in components:
                hits = await search_budgets(
                    self._retriever,
                    query=component["query"],
                    filters={
                        "component_type": component["category"],
                        "client_sector": None,
                        "date_range": None,
                        "top_k": 5,
                    },
                )
                component_hits[component["name"]] = hits
                all_hits.extend(hits)

            return {
                "component_hits": component_hits,
                "budget_hits": all_hits,
                "agent_contributions": [
                    {
                        "step": int(state.get("supervisor_steps") or 1),
                        "agent": "budget_searcher",
                        "action": "tool:search_budgets",
                        "tool": "search_budgets",
                        "outcome": "ok",
                        "summary": f"Found {len(all_hits)} historical references across {len(components)} components.",
                        "args_digest": self._digest_payload({"components": [c["name"] for c in components]}),
                        "duration_ms": int((perf_counter() - started) * 1000),
                    }
                ],
                "trace": [
                    {
                        "reasoning": "The budget searcher can only use search_budgets, limiting retrieval privileges.",
                        "action": "budget_searcher.search_budgets",
                        "observation": f"Found {len(all_hits)} historical references across {len(components)} components.",
                    }
                ],
            }

    def estimate_generator(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        components = state.get("components", [])
        component_hits = state.get("component_hits", {})

        with logfire.span("agentic.langgraph.estimate_generator", estimation_id=estimation_id):
            allowed, denied_contribution = validate_action(
                agent="estimate_generator",
                tool="calculate_estimate",
                step=int(state.get("supervisor_steps") or 0),
            )
            if not allowed:
                return {
                    "agent_contributions": [denied_contribution],
                    "validation_errors": [denied_contribution["summary"]],
                }
            started = perf_counter()
            estimate_components: list[dict[str, object]] = []
            for component in components:
                hits = component_hits.get(component["name"], [])
                reference_amounts = [float(hit.get("amount", 0.0)) for hit in hits if hit.get("amount") is not None]
                estimate_components.append(
                    {
                        "name": component["name"],
                        "reference_amounts": reference_amounts,
                    }
                )

            estimate = calculate_estimate(estimate_components)
            return {
                "structured_estimate": estimate.model_dump(),
                "agent_contributions": [
                    {
                        "step": int(state.get("supervisor_steps") or 1),
                        "agent": "estimate_generator",
                        "action": "tool:calculate_estimate",
                        "tool": "calculate_estimate",
                        "outcome": "ok",
                        "summary": f"Generated {estimate.total_amount} {estimate.unit} across {len(estimate.components)} components.",
                        "args_digest": self._digest_payload({"component_count": len(estimate_components)}),
                        "duration_ms": int((perf_counter() - started) * 1000),
                    }
                ],
                "trace": [
                    {
                        "reasoning": "The estimate generator can only calculate from selected historical references.",
                        "action": "estimate_generator.calculate_estimate",
                        "observation": f"Generated estimate with {len(estimate.components)} components and total {estimate.total_amount} {estimate.unit}.",
                    }
                ],
            }

    def coherence_validator(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        estimate_payload = dict(state.get("structured_estimate", {}))

        with logfire.span("agentic.langgraph.coherence_validator", estimation_id=estimation_id):
            allowed, denied_contribution = validate_action(
                agent="coherence_validator",
                tool="validate_estimate",
                step=int(state.get("supervisor_steps") or 0),
            )
            if not allowed:
                return {
                    "agent_contributions": [denied_contribution],
                    "validation_errors": [denied_contribution["summary"]],
                }
            started = perf_counter()
            estimate = AgenticEstimate.model_validate(estimate_payload)
            validation = validate_estimate(estimate)
            confidence = float(validation["confidence"])
            status: Literal["validated", "needs_review"] = "validated" if not validation["errors"] else "needs_review"
            consolidated = estimate.model_copy(update={"status": status, "confidence": confidence, "validation": validation})

            return {
                "structured_estimate": consolidated.model_dump(),
                "validation": validation,
                "validation_errors": list(validation["errors"]),
                "confidence": confidence,
                "status": status,
                "agent_contributions": [
                    {
                        "step": int(state.get("supervisor_steps") or 1),
                        "agent": "coherence_validator",
                        "action": "tool:validate_estimate",
                        "tool": "validate_estimate",
                        "outcome": "ok",
                        "summary": f"Validated estimate with confidence {confidence:.2f} and {len(validation['errors'])} issue(s).",
                        "args_digest": self._digest_payload({"component_count": len(estimate.components)}),
                        "duration_ms": int((perf_counter() - started) * 1000),
                    }
                ],
                "trace": [
                    {
                        "reasoning": "The coherence validator can only validate the generated estimate.",
                        "action": "coherence_validator.validate_estimate",
                        "observation": f"Validation status: {status}. Confidence: {confidence:.2f}.",
                    }
                ],
            }

    def human_review_gate(self, state: EstimationGraphState) -> Command[Literal["finalize"]]:
        if not requires_human_review(state):
            return Command(goto="finalize")

        decision = interrupt(build_human_review_interrupt_payload(state))
        return Command(
            goto="finalize",
            update=build_human_decision_update(
                state=state,
                decision=decision,
                digest_payload=self._digest_payload,
            ),
        )

    def finalize(self, state: EstimationGraphState) -> dict[str, object]:
        estimate = AgenticEstimate.model_validate(dict(state.get("structured_estimate", {})))
        decision = state.get("human_decision") if isinstance(state.get("human_decision"), dict) else {}
        update_payload = build_finalize_update_payload(state=state, decision=decision)

        consolidated = estimate.model_copy(update=update_payload)
        final_text = self._render_final_text(consolidated)
        return {
            "structured_estimate": consolidated.model_dump(),
            "status": consolidated.status,
            "final_text": final_text,
            "trace": [
                {
                    "reasoning": "Finalize consolidates validation and any human decision into the public result.",
                    "action": "finalize",
                    "observation": f"Final status: {consolidated.status}.",
                }
            ],
        }

    @staticmethod
    def _classify_components(requirements: list[str]) -> list[ComponentSpec]:
        keyword_map: dict[str, tuple[str, str]] = {
            "backend": ("Backend API", "backend"),
            "api": ("Backend API", "backend"),
            "frontend": ("Frontend Web", "frontend"),
            "web": ("Frontend Web", "frontend"),
            "mobile": (MOBILE_COMPONENT, "mobile"),
            "android": (MOBILE_COMPONENT, "mobile"),
            "ios": (MOBILE_COMPONENT, "mobile"),
            "erp": ("ERP Integration", "integration"),
            "integrat": ("ERP Integration", "integration"),
            "data": ("Data Pipeline", "data"),
            "etl": ("Data Pipeline", "data"),
            "qa": ("QA and Testing", "qa"),
            "test": ("QA and Testing", "qa"),
            "devops": ("DevOps and Deployment", "devops"),
            "deploy": ("DevOps and Deployment", "devops"),
        }

        component_map: dict[str, ComponentSpec] = {}
        for requirement in requirements:
            lower_req = requirement.lower()
            matched = False
            for keyword, (name, category) in keyword_map.items():
                if keyword in lower_req:
                    if name not in component_map:
                        component_map[name] = {
                            "name": name,
                            "category": category,
                            "query": f"{name} {requirement}",
                        }
                    matched = True
            if not matched and GENERAL_SCOPE_COMPONENT not in component_map:
                component_map[GENERAL_SCOPE_COMPONENT] = {
                    "name": GENERAL_SCOPE_COMPONENT,
                    "category": "general",
                    "query": requirement,
                }

        return list(component_map.values())

    def _route_with_audit(
        self,
        *,
        goto: AgentNode,
        reason: str,
        step: int,
        source: Literal["llm", "fallback", "limit"],
        confidence: Literal["low", "medium", "high"] | None,
    ) -> Command[AgentNode]:
        return Command(
            goto=goto,
            update=build_route_audit_update(
                goto=goto,
                reason=reason,
                step=step,
                source=source,
                confidence=confidence,
                digest_payload=self._digest_payload,
            ),
        )

    async def _route_with_model(self, state: EstimationGraphState) -> SupervisorRoutingDecision:
        from app.foundation.llm.litellm_service import litellm_router_service

        decision, _ = await litellm_router_service.complete_structured(
            messages=[
                {"role": "system", "content": SUPERVISOR_SYSTEM_PROMPT},
                {"role": "user", "content": summarize_state_for_router(state)},
            ],
            response_model=SupervisorRoutingDecision,
            max_retries=2,
        )
        return decision

    @staticmethod
    def _digest_payload(payload: dict[str, object]) -> str:
        canonical = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

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