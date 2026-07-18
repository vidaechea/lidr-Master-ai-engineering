from __future__ import annotations

import operator
import re
from typing import Annotated, Any, Literal, TypedDict

import logfire
import structlog
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from app.agents.schemas import AgenticEstimate
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


class ComponentSpec(TypedDict):
    name: str
    category: str
    query: str


class GraphTraceEntry(TypedDict):
    reasoning: str
    action: str
    observation: str


class AgentContribution(TypedDict):
    agent: str
    summary: str


class EstimationGraphState(TypedDict, total=False):
    estimation_id: str
    transcription: str
    requirements: list[str]
    components: list[ComponentSpec]
    component_hits: dict[str, list[dict[str, object]]]
    budget_hits: Annotated[list[dict[str, object]], operator.add]
    validation_errors: Annotated[list[str], operator.add]
    trace: Annotated[list[GraphTraceEntry], operator.add]
    agent_contributions: Annotated[list[AgentContribution], operator.add]
    structured_estimate: dict[str, object]
    validation: dict[str, object]
    confidence: float
    status: Literal["validated", "needs_review", "awaiting_human_review"]
    human_decision: dict[str, object]
    final_text: str


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

    def supervisor(self, state: EstimationGraphState) -> Command[AgentNode]:
        if not state.get("requirements") or not state.get("components"):
            return self._route("requirements_extractor", "Extract requirements and classify components.")
        if not state.get("component_hits"):
            return self._route("budget_searcher", "Search historical budgets for each component.")
        if not state.get("structured_estimate"):
            return self._route("estimate_generator", "Generate the deterministic estimate.")
        if not state.get("validation"):
            return self._route("coherence_validator", "Validate estimate coherence and confidence.")
        if self._requires_human_review(state) and not state.get("human_decision"):
            return self._route("human_review_gate", "Pause for human review because confidence is low.")
        return self._route("finalize", "Finalize the estimate response.")

    def requirements_extractor(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        transcription = state["transcription"]

        with logfire.span("agentic.langgraph.requirements_extractor", estimation_id=estimation_id):
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
                        "agent": "requirements_extractor",
                        "summary": f"Extracted {len(requirements)} requirements and {len(components)} components.",
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
            self._validate_action("budget_searcher", "search_budgets")
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
                        "agent": "budget_searcher",
                        "summary": f"Found {len(all_hits)} historical references across {len(components)} components.",
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
            self._validate_action("estimate_generator", "calculate_estimate")
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
                        "agent": "estimate_generator",
                        "summary": f"Generated {estimate.total_amount} {estimate.unit} across {len(estimate.components)} components.",
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
            self._validate_action("coherence_validator", "validate_estimate")
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
                        "agent": "coherence_validator",
                        "summary": f"Validated estimate with confidence {confidence:.2f} and {len(validation['errors'])} issue(s).",
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
        if not self._requires_human_review(state):
            return Command(goto="finalize")

        decision = interrupt(
            {
                "reason": "low_confidence_estimate",
                "estimate": state.get("structured_estimate"),
                "confidence": state.get("confidence"),
                "validation": state.get("validation", {}),
                "threshold": settings.agentic_estimation_confidence_threshold,
            }
        )
        return Command(
            goto="finalize",
            update={
                "human_decision": decision,
                "trace": [
                    {
                        "reasoning": "A persisted human decision was received after the low-confidence interrupt.",
                        "action": "human_review_gate.resume",
                        "observation": "Human decision folded into graph state.",
                    }
                ],
            },
        )

    def finalize(self, state: EstimationGraphState) -> dict[str, object]:
        estimate = AgenticEstimate.model_validate(dict(state.get("structured_estimate", {})))
        decision = state.get("human_decision") or {}
        update_payload: dict[str, object] = {}

        action = str(decision.get("action") or decision.get("decision") or "approve")
        overrides = decision.get("estimate_overrides")
        if isinstance(overrides, dict):
            update_payload.update(overrides)

        if action == "reject":
            update_payload["status"] = "needs_review"
        elif decision:
            update_payload["status"] = "validated"
        elif self._requires_human_review(state) and not decision:
            update_payload["status"] = "awaiting_human_review"
        else:
            update_payload["status"] = "validated" if not state.get("validation_errors") else "needs_review"

        if state.get("confidence") is not None:
            update_payload["confidence"] = state["confidence"]
        if state.get("validation"):
            update_payload["validation"] = state["validation"]

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

    @staticmethod
    def _route(goto: AgentNode, reason: str) -> Command[AgentNode]:
        return Command(
            goto=goto,
            update={
                "trace": [
                    {
                        "reasoning": reason,
                        "action": f"supervisor.route.{goto}",
                        "observation": f"Supervisor routed to {goto}.",
                    }
                ]
            },
        )

    @staticmethod
    def _requires_human_review(state: EstimationGraphState) -> bool:
        validation = state.get("validation") or {}
        confidence = state.get("confidence")
        if confidence is not None and confidence < settings.agentic_estimation_confidence_threshold:
            return True
        return bool(
            validation.get("no_historical_precedent")
            or validation.get("outside_historical_range")
        )

    @staticmethod
    def _validate_action(agent: str, tool: str) -> None:
        allowed_tools = {
            "requirements_extractor": set(),
            "budget_searcher": {"search_budgets"},
            "estimate_generator": {"calculate_estimate"},
            "coherence_validator": {"validate_estimate"},
            "supervisor": set(),
        }
        if tool not in allowed_tools.get(agent, set()):
            log.warning("agent_tool_rejected", agent=agent, tool=tool)
            raise PermissionError(f"Agent '{agent}' cannot use tool '{tool}'.")
        log.info("agent_tool_allowed", agent=agent, tool=tool)

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