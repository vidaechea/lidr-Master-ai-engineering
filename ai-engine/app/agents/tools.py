from __future__ import annotations

import json
import re
from statistics import mean

from app.agents.schemas import (
    AgenticEstimate,
    EstimatedComponent,
    HistoricalBudgetHit,
    SearchBudgetsFilters,
)
from app.generation.rag.schemas import EstimationQuery
from app.generation.rag.retriever_service import SemanticRetriever


SEARCH_BUDGETS_TOOL: dict = {
    "type": "function",
    "name": "search_budgets",
    "description": (
        "Search historical budget records for a specific project component or requirement. "
        "Use this when the transcript mentions a component that needs its own historical references, "
        "or when you need separate evidence for different parts of the estimate."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Natural-language search text describing the component or requirement.",
            },
            "filters": {
                "type": ["object", "null"],
                "description": "Optional filters to narrow the search to a component type, sector, or year range.",
                "properties": {
                    "component_type": {
                        "type": ["string", "null"],
                        "description": "Component family or domain to bias the search, such as backend, ERP integration, or mobile app.",
                    },
                    "client_sector": {
                        "type": ["string", "null"],
                        "description": "Optional client sector filter for the historical corpus.",
                    },
                    "date_range": {
                        "type": ["object", "null"],
                        "description": "Optional inclusive year range for the historical records.",
                        "properties": {
                            "from_year": {
                                "type": ["integer", "null"],
                                "description": "Lower bound year, inclusive.",
                                "minimum": 2000,
                                "maximum": 2100,
                            },
                            "to_year": {
                                "type": ["integer", "null"],
                                "description": "Upper bound year, inclusive.",
                                "minimum": 2000,
                                "maximum": 2100,
                            },
                        },
                        "required": ["from_year", "to_year"],
                        "additionalProperties": False,
                    },
                    "top_k": {
                        "type": ["integer", "null"],
                        "description": "Maximum number of historical matches to return.",
                    },
                },
                "required": ["component_type", "client_sector", "date_range", "top_k"],
                "additionalProperties": False,
            },
        },
        "required": ["query", "filters"],
        "additionalProperties": False,
    },
}


CALCULATE_ESTIMATE_TOOL: dict = {
    "type": "function",
    "name": "calculate_estimate",
    "description": (
        "Calculate a deterministic estimate from component names and their historical reference amounts. "
        "Use this only after you have collected enough references for every component you want to include in the final estimate."
    ),
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": "Component list with historical reference amounts already selected by the agent.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Component name used in the final estimate.",
                        },
                        "reference_amounts": {
                            "type": "array",
                            "description": "Reference amounts used to compute the estimate for this component.",
                            "items": {
                                "type": "number",
                            },
                        },
                    },
                    "required": ["name", "reference_amounts"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["components"],
        "additionalProperties": False,
    },
}


def build_agent_tools() -> list[dict]:
    return [SEARCH_BUDGETS_TOOL, CALCULATE_ESTIMATE_TOOL]


async def search_budgets(
    retriever: SemanticRetriever,
    *,
    query: str,
    filters: dict | None = None,
) -> list[dict[str, object]]:
    parsed_filters = SearchBudgetsFilters.model_validate(filters or {})

    search_text_parts = [query.strip()]
    if parsed_filters.component_type:
        search_text_parts.append(parsed_filters.component_type.strip())
    if parsed_filters.client_sector:
        search_text_parts.append(parsed_filters.client_sector.strip())

    date_range = parsed_filters.date_range
    year_from = date_range.from_year if date_range else None
    year_to = date_range.to_year if date_range else None
    top_k = parsed_filters.top_k or 5

    retrieval_query = EstimationQuery(
        search_text=" ".join(part for part in search_text_parts if part),
        sector=parsed_filters.client_sector,
        year_from=year_from,
        year_to=year_to,
        chunk_types=[],
    )

    try:
        result = await retriever.search_with_query(
            query=retrieval_query,
            k=top_k,
            mode="hybrid",
            rerank=True,
        )
    except RuntimeError as exc:
        message = str(exc)
        if (
            "Reranking requested" not in message
            and "sentence-transformers is required" not in message
        ):
            raise
        result = await retriever.search_with_query(
            query=retrieval_query,
            k=top_k,
            mode="hybrid",
            rerank=False,
        )

    hits: list[dict[str, object]] = []
    for chunk in result.chunks:
        amount = _extract_reference_amount(chunk.content, chunk.metadata)
        hit = HistoricalBudgetHit(
            source_id=chunk.source_id,
            budget_id=str(chunk.metadata.get("budget_id")) if chunk.metadata.get("budget_id") is not None else None,
            component_name=_extract_component_name(chunk.content, chunk.metadata),
            amount=amount,
            unit="hours",
            year=_safe_int(chunk.metadata.get("year")),
            client_sector=_maybe_str(chunk.metadata.get("client_sector")),
            main_technology=_maybe_str(chunk.metadata.get("main_technology")),
            distance=chunk.distance,
            metadata=dict(chunk.metadata),
        )
        hits.append(hit.model_dump())

    return hits


def calculate_estimate(components: list[dict[str, object]]) -> AgenticEstimate:
    estimated_components: list[EstimatedComponent] = []
    total_amount = 0.0

    for component in components:
        name = str(component["name"])
        reference_amounts = [float(value) for value in component.get("reference_amounts", [])]
        estimated_amount = round(mean(reference_amounts), 2) if reference_amounts else 0.0
        total_amount += estimated_amount
        estimated_components.append(
            EstimatedComponent(
                name=name,
                reference_amounts=reference_amounts,
                estimated_amount=estimated_amount,
                unit="hours",
                reference_count=len(reference_amounts),
            )
        )

    assumptions = [
        "Each component estimate is the arithmetic mean of the selected historical references.",
        "Reference amounts are treated as comparable effort units from the historical corpus.",
    ]

    return AgenticEstimate(
        components=estimated_components,
        total_amount=round(total_amount, 2),
        unit="hours",
        method="arithmetic_mean",
        assumptions=assumptions,
    )


def serialize_calculate_estimate_output(components: list[dict[str, object]]) -> str:
    return calculate_estimate(components).model_dump_json()


def _extract_component_name(content: str, metadata: dict[str, object]) -> str:
    for key in ("component_name", "component_id"):
        value = metadata.get(key)
        if value:
            return str(value)

    match = re.search(r"^Component:\s*(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()

    return str(metadata.get("budget_id") or "Historical component")


def _extract_reference_amount(content: str, metadata: dict[str, object]) -> float:
    raw_value = metadata.get("estimated_hours")
    if raw_value is None:
        match = re.search(r"Estimated hours:\s*(\d+(?:\.\d+)?)", content)
        raw_value = match.group(1) if match else 0
    return float(raw_value)


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_str(value: object) -> str | None:
    return str(value) if value is not None else None
