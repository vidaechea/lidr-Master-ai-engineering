from __future__ import annotations

import operator
import re
from typing import Annotated, Any, Literal, TypedDict

import logfire
import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.schemas import AgenticEstimate
from app.agents.tools import calculate_estimate, search_budgets
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)

MOBILE_COMPONENT = "Mobile App"
GENERAL_SCOPE_COMPONENT = "General Scope"


class ComponentSpec(TypedDict):
    name: str
    category: str
    query: str


class GraphTraceEntry(TypedDict):
    reasoning: str
    action: str
    observation: str


class EstimationGraphState(TypedDict, total=False):
    estimation_id: str
    transcription: str
    requirements: list[str]
    components: list[ComponentSpec]
    component_hits: dict[str, list[dict[str, object]]]
    budget_hits: Annotated[list[dict[str, object]], operator.add]
    validation_errors: Annotated[list[str], operator.add]
    trace: Annotated[list[GraphTraceEntry], operator.add]
    structured_estimate: dict[str, object]
    status: Literal["validated", "needs_review"]
    final_text: str


class SequentialEstimationGraph:
    def __init__(self, *, retriever: SemanticRetriever) -> None:
        self._retriever = retriever

    def build(self, *, checkpointer: Any | None = None):
        graph_builder = StateGraph(EstimationGraphState)

        graph_builder.add_node("extract_requirements", self.extract_requirements)
        graph_builder.add_node("classify_components", self.classify_components)
        graph_builder.add_node("search_budgets", self.search_budgets)
        graph_builder.add_node("generate_estimate", self.generate_estimate)
        graph_builder.add_node("validate_and_consolidate", self.validate_and_consolidate)

        graph_builder.add_edge(START, "extract_requirements")
        graph_builder.add_edge("extract_requirements", "classify_components")
        graph_builder.add_edge("classify_components", "search_budgets")
        graph_builder.add_edge("search_budgets", "generate_estimate")
        graph_builder.add_edge("generate_estimate", "validate_and_consolidate")
        graph_builder.add_edge("validate_and_consolidate", END)

        return graph_builder.compile(checkpointer=checkpointer)

    def extract_requirements(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        transcription = state["transcription"]

        with logfire.span("agentic.langgraph.extract_requirements", estimation_id=estimation_id):
            raw_chunks = re.split(r"[\n\r\.\!\?;]+", transcription)
            requirements = [chunk.strip() for chunk in raw_chunks if len(chunk.strip()) >= 15]
            if not requirements:
                requirements = [transcription.strip()[:240]]

            return {
                "requirements": requirements,
                "trace": [
                    {
                        "reasoning": "Extract explicit scope statements from the transcript before grouping work.",
                        "action": "extract_requirements",
                        "observation": f"Extracted {len(requirements)} requirements.",
                    }
                ],
            }

    def classify_components(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        requirements = state.get("requirements", [])

        with logfire.span("agentic.langgraph.classify_components", estimation_id=estimation_id):
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

            components = list(component_map.values())
            return {
                "components": components,
                "trace": [
                    {
                        "reasoning": "Group requirements into estimate components to query references per component.",
                        "action": "classify_components",
                        "observation": f"Classified {len(components)} components.",
                    }
                ],
            }

    async def search_budgets(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        components = state.get("components", [])

        with logfire.span("agentic.langgraph.search_budgets", estimation_id=estimation_id):
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
                "trace": [
                    {
                        "reasoning": "Retrieve historical references one component at a time to keep the flow deterministic.",
                        "action": "search_budgets",
                        "observation": f"Found {len(all_hits)} historical references across {len(components)} components.",
                    }
                ],
            }

    def generate_estimate(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        components = state.get("components", [])
        component_hits = state.get("component_hits", {})

        with logfire.span("agentic.langgraph.generate_estimate", estimation_id=estimation_id):
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
                "trace": [
                    {
                        "reasoning": "Consolidate component references into a deterministic estimate.",
                        "action": "generate_estimate",
                        "observation": f"Generated estimate with {len(estimate.components)} components and total {estimate.total_amount} {estimate.unit}.",
                    }
                ],
            }

    def validate_and_consolidate(self, state: EstimationGraphState) -> dict[str, object]:
        estimation_id = state["estimation_id"]
        estimate_payload = dict(state.get("structured_estimate", {}))

        with logfire.span("agentic.langgraph.validate_and_consolidate", estimation_id=estimation_id):
            estimate = AgenticEstimate.model_validate(estimate_payload)
            errors: list[str] = []
            if estimate.total_amount <= 0:
                errors.append("Estimated total amount is zero or negative.")

            missing_references = [component.name for component in estimate.components if component.reference_count == 0]
            if missing_references:
                errors.append(
                    "Missing historical references for: " + ", ".join(missing_references)
                )

            status: Literal["validated", "needs_review"] = "validated" if not errors else "needs_review"
            consolidated = estimate.model_copy(update={"status": status})
            final_text = self._render_final_text(consolidated)

            return {
                "structured_estimate": consolidated.model_dump(),
                "validation_errors": errors,
                "status": status,
                "final_text": final_text,
                "trace": [
                    {
                        "reasoning": "Validate estimate completeness and mark output status for downstream consumers.",
                        "action": "validate_and_consolidate",
                        "observation": f"Validation status: {status}. Issues: {len(errors)}.",
                    }
                ],
            }

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
