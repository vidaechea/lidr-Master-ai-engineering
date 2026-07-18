from __future__ import annotations

import re
from typing import Any

import structlog
from pydantic import BaseModel, Field, field_validator, model_validator

from app.domain.schemas.agent_trace import AgentStep, AgentTrace
from app.foundation.llm.error_mapper import LLMServiceError
from app.generation.rag.schemas import (
    EstimateModule,
    EstimateTask,
    EstimationQuery,
    GenerateStageResponse,
    RagPipelineEstimate,
    TaskHoursEstimate,
    TaskHoursModuleInput,
    TaskHoursTaskInput,
    TaskNeighbor,
    TaskHoursResult,
)
from app.generation.rag.task_hours import compose_task_search_text, distance_weighted_consensus, estimate_all
from app.generation.rag.retriever_service import SemanticRetriever

log = structlog.get_logger(__name__)

_LOW_RELIABILITY = 0.35


class AgentStructureTask(BaseModel):
    name: str = Field(min_length=4, max_length=90)
    description: str = Field(min_length=20, max_length=500)

    @field_validator("name", "description")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AgentStructureModule(BaseModel):
    name: str = Field(min_length=4, max_length=80)
    tasks: list[AgentStructureTask] = Field(min_length=1, max_length=6)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class AgentStructureProposal(BaseModel):
    modules: list[AgentStructureModule] = Field(min_length=1, max_length=10)
    assumptions: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def reject_placeholder_structure(self) -> "AgentStructureProposal":
        for module in self.modules:
            if module.name.lower().startswith("task "):
                raise ValueError("module names must describe a business or technical capability")
            for task in module.tasks:
                if task.name.lower() in {"task", "task 1", "task 2", "implementation", "development"}:
                    raise ValueError("task names must be specific to the transcript")
        return self


_STRUCTURE_SYSTEM_PROMPT = """You are a senior software delivery analyst.
Extract an editable work breakdown structure from a project transcript.

Rules:
- Create modules and tasks only from requirements explicitly present or strongly implied in the transcript.
- Do not use generic placeholders like Task 1, implementation, development, or module names copied from the transcript.
- Each task description must be concrete, actionable, and mention the feature, integration, workflow, data object, user role, constraint, or non-functional requirement it covers.
- Do not estimate hours. Historical retrieval will estimate hours later.
- Keep the structure compact enough for human review: 3-8 modules, 1-5 tasks per module.
- Use English for module/task names and descriptions.
"""


def _structure_user_prompt(query: EstimationQuery, *, persona: str | None) -> str:
    persona_text = f"\nPersona or estimation lens: {persona.strip()}\n" if persona and persona.strip() else ""
    filters = []
    if query.sector:
        filters.append(f"sector={query.sector}")
    if query.year_from or query.year_to:
        filters.append(f"year_range={query.year_from or '*'}-{query.year_to or '*'}")
    if query.keywords:
        filters.append("keywords=" + ", ".join(query.keywords[:12]))
    filter_text = "\nKnown retrieval hints: " + "; ".join(filters) if filters else ""
    return (
        "Build the work breakdown structure for this transcript. "
        "Return modules with specific tasks and descriptions only."
        f"{persona_text}{filter_text}\n\n"
        "Transcript:\n"
        f"{query.search_text[:8_000]}"
    )

TaskHint = tuple[str, tuple[str, ...], str]
ModuleHint = tuple[str, tuple[str, ...], tuple[TaskHint, ...]]


_STRUCTURE_HINTS: tuple[ModuleHint, ...] = (
    (
        "Discovery and Analysis",
        ("discovery", "requirements", "workshop", "brief", "alcance", "requisitos", "descubrimiento"),
        (
            (
                "Scope and phasing workshop",
                ("phase one", "phase two", "phase three", "september", "christmas", "budget", "scope"),
                "Clarify MVP scope, delivery phases, launch deadline, budget guardrails, and explicit exclusions.",
            ),
            (
                "Technical discovery and acceptance criteria",
                ("technical", "deep-dive", "architecture", "requirements", "docs", "spec"),
                "Review existing systems, integration documents, constraints, and acceptance criteria with the technical stakeholders.",
            ),
        ),
    ),
    (
        "Backend API",
        ("backend", "api", "endpoint", "service", "fastapi", "node", "java", "django", "reservation", "availability"),
        (
            (
                "Reservation engine and availability rules",
                ("reservation", "availability", "table", "slot", "turn time", "wait list", "overbook", "double-book"),
                "Implement restaurant layouts, table capacity, service slots, wait-list rules, and availability checks.",
            ),
            (
                "Concurrency-safe booking persistence",
                ("concurrent", "race", "double-book", "exclusion", "tstzrange", "gist", "postgres"),
                "Model reservations in Postgres with range constraints so concurrent writes cannot double-book a table.",
            ),
            (
                "Multi-tenant operational API",
                ("tenant", "restaurant", "multi-tenant", "rls", "regional", "hq", "manager"),
                "Expose APIs with tenant isolation, role-scoped access, and operational views for restaurant, regional, and HQ users.",
            ),
        ),
    ),
    (
        "Frontend Web",
        ("frontend", "web", "dashboard", "portal", "angular", "react", "ui", "ux"),
        (
            (
                "Customer booking PWA",
                ("customer", "book", "mobile", "pwa", "three clicks", "website"),
                "Build a mobile-first booking flow for customers with fast restaurant, party-size, slot, and confirmation steps.",
            ),
            (
                "Manager tablet floor operations",
                ("manager", "tablet", "ipad", "floor", "no-show", "reassign", "walk-in"),
                "Create a tablet-optimized manager interface for floor plans, walk-ins, no-shows, table reassignment, and manual adjustments.",
            ),
            (
                "Role-based dashboards",
                ("dashboard", "analytics", "reporting", "region", "chef", "manager", "hq"),
                "Design dashboards for HQ, regional managers, restaurant managers, and chefs with role-specific metrics and filters.",
            ),
        ),
    ),
    (
        "Mobile App",
        ("mobile", "android", "ios", "app móvil", "app movil", "react native", "flutter"),
        (
            (
                "Mobile-responsive booking experience",
                ("mobile", "pwa", "responsive", "website", "customer"),
                "Ensure the customer booking journey works cleanly on mobile web/PWA without native-app maintenance overhead.",
            ),
        ),
    ),
    (
        "ERP Integration",
        ("erp", "integration", "integración", "integracion", "sap", "workday", "salesforce", "connector", "pos", "loyalty", "hubspot"),
        (
            (
                "Loyalty service lookup integration",
                ("loyalty", "points", "tier", "oauth2", "spring boot", "balance", "redemption"),
                "Integrate with the existing loyalty REST service for customer matching, tier lookup, points visibility, caching, and graceful degradation.",
            ),
            (
                "BCN-Touch POS enrichment relay",
                ("bcn-touch", "pos", "patch_ticket", "reservation_id", "customer_id", "vpn", "relay"),
                "Deliver reservation and customer identifiers to local BCN-Touch instances through a pull-based restaurant relay.",
            ),
            (
                "HubSpot customer sync",
                ("hubspot", "marketing", "opt-in", "dedup", "email", "segmentation"),
                "Synchronize customer profiles, visit attributes, loyalty tags, and marketing opt-in state with HubSpot.",
            ),
        ),
    ),
    (
        "Data Pipeline",
        ("data", "etl", "pipeline", "analytics", "reporting", "bi", "datos", "migration", "legacy"),
        (
            (
                "Legacy reservation data migration",
                ("migration", "legacy", "barcelona", "postgresql", "import", "notes", "free-text"),
                "Extract, clean, classify, and import legacy Barcelona reservation/customer data while preserving manager notes.",
            ),
            (
                "Operational analytics aggregation",
                ("analytics", "reporting", "dashboard", "no-show", "conversion", "repeat", "average", "region"),
                "Build near-real-time aggregations for bookings, no-shows, conversion, party size, repeat rate, visit cadence, and regional slicing.",
            ),
        ),
    ),
    (
        "Authentication and Security",
        ("auth", "authentication", "oauth", "login", "jwt", "sso", "security", "seguridad", "permisos"),
        (
            (
                "Role-based access control",
                ("role", "roles", "manager", "regional", "hq", "chef", "tenant", "rls"),
                "Implement authentication and authorization for customer, restaurant manager, regional manager, chef, and HQ access levels.",
            ),
            (
                "GDPR and DSAR workflows",
                ("gdpr", "dsar", "erasure", "access", "portability", "export", "pdf", "privacy"),
                "Provide customer data access, export, erasure, portability, consent handling, and audit-friendly privacy operations.",
            ),
            (
                "Accessibility compliance",
                ("accessibility", "wcag", "aa", "public bodies"),
                "Bake WCAG AA requirements into design, implementation, and acceptance testing for public-sector event bookings.",
            ),
        ),
    ),
    (
        "QA and Testing",
        ("qa", "test", "testing", "quality", "calidad", "pruebas", "uat"),
        (
            (
                "Integration and regression test suite",
                ("integration", "regression", "test", "testing", "pos", "loyalty", "hubspot"),
                "Cover reservation flows, loyalty fallback, POS relay events, HubSpot sync, payments, and data migration with automated regression tests.",
            ),
            (
                "Soft-launch acceptance testing",
                ("soft launch", "september", "uat", "flagship", "buffer", "launch"),
                "Run UAT and operational rehearsal for the Madrid flagship rollout before the September production target.",
            ),
        ),
    ),
    (
        "DevOps and Deployment",
        ("devops", "deploy", "deployment", "ci/cd", "docker", "kubernetes", "infra", "release"),
        (
            (
                "AWS ECS deployment foundation",
                ("aws", "ecs", "fargate", "container", "docker", "madrid", "eu-south-2"),
                "Set up containerized environments on AWS Madrid with ECS/Fargate, secrets, networking, and release automation.",
            ),
            (
                "Redis caching and scalability setup",
                ("redis", "elasticache", "cache", "availability", "qps", "autoscaling", "peak"),
                "Add Redis caching, autoscaling, and performance guardrails for bursty availability lookups and reservation writes.",
            ),
            (
                "Observability and operational runbooks",
                ("observability", "monitoring", "logs", "runbook", "incident", "ops"),
                "Prepare monitoring, alerts, logs, dashboards, and runbooks for launch and restaurant support.",
            ),
        ),
    ),
)


def _should_recover(estimate: TaskHoursEstimate) -> bool:
    if not estimate.has_match:
        return True
    if estimate.hours_range is not None:
        return True
    if estimate.reliability is not None and estimate.reliability < _LOW_RELIABILITY:
        return True
    return False


def _extract_estimated_hours(content: str, metadata: dict[str, object]) -> int | None:
    raw_value = metadata.get("estimated_hours")
    if raw_value is None:
        match = re.search(r"Estimated hours:\s*(\d+(?:\.\d+)?)", content)
        raw_value = match.group(1) if match else None
    if raw_value is None:
        return None
    try:
        return int(float(raw_value))
    except (TypeError, ValueError):
        return None


def _build_neighbor_list(retrieval_chunks, *, distance_threshold: float) -> list[TaskNeighbor]:
    neighbors: list[TaskNeighbor] = []
    for chunk in retrieval_chunks:
        if chunk.distance > distance_threshold:
            continue
        hours = _extract_estimated_hours(chunk.content, chunk.metadata)
        if hours is None:
            continue
        neighbors.append(
            TaskNeighbor(
                source_id=chunk.source_id,
                budget_id=str(chunk.metadata.get("budget_id")) if chunk.metadata.get("budget_id") is not None else None,
                estimated_hours=hours,
                distance=chunk.distance,
            )
        )
    return neighbors


async def _search_task_neighbors(
    *,
    retriever: SemanticRetriever,
    module: str,
    task: TaskHoursTaskInput,
    top_k: int,
    distance_threshold: float,
):
    query = EstimationQuery(
        search_text=compose_task_search_text(module, task.name, task.description),
        sector=None,
        year_from=None,
        year_to=None,
        chunk_types=["budget_component"],
        keywords=[],
    )
    try:
        return await retriever.search_with_query(
            query=query,
            k=top_k,
            distance_threshold=distance_threshold,
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
        return await retriever.search_with_query(
            query=query,
            k=top_k,
            distance_threshold=distance_threshold,
            mode="hybrid",
            rerank=False,
        )


def _find_task_input(modules: list[TaskHoursModuleInput], module_name: str, task_name: str) -> TaskHoursTaskInput | None:
    for module in modules:
        if module.name != module_name:
            continue
        for task in module.tasks:
            if task.name == task_name:
                return task
    return None


def _propose_modules(query: EstimationQuery) -> list[EstimateModule]:
    """Build a lightweight structure from query signals.

    This is a first implementation slice to expose the Session 12 API surface.
    It prefers explicit query keywords, then extracts common delivery domains
    from the brief so task-hours retrieval receives focused search text.
    """
    labels = [keyword.strip() for keyword in query.keywords if keyword.strip()]
    if labels:
        return [
            EstimateModule(
                name=label[:80],
                engineer_days=0.0,
                tasks=[
                    EstimateTask(
                        name=f"Estimate {label[:64]}",
                        engineer_days=0.0,
                        description=f"Estimate implementation effort for {label}.",
                    )
                ],
            )
            for label in labels
        ]

    search_text = query.search_text.strip()
    lower_text = search_text.lower()
    modules: list[EstimateModule] = []
    seen_names: set[str] = set()
    for module_name, keywords, task_hints in _STRUCTURE_HINTS:
        if module_name in seen_names:
            continue
        if not any(_contains_keyword(lower_text, keyword) for keyword in keywords):
            continue
        tasks = _tasks_from_hints(lower_text=lower_text, task_hints=task_hints)
        modules.append(
            EstimateModule(
                name=module_name,
                engineer_days=0.0,
                tasks=tasks,
            )
        )
        seen_names.add(module_name)

    if modules:
        return modules

    fallback_label = _fallback_module_label(search_text)
    return [
        EstimateModule(
            name=fallback_label,
            engineer_days=0.0,
            tasks=[
                EstimateTask(
                    name="Scope estimation",
                    engineer_days=0.0,
                    description="Estimate the general delivery scope when no specific domain is explicit.",
                )
            ],
        )
    ]


def _tasks_from_hints(*, lower_text: str, task_hints: tuple[TaskHint, ...]) -> list[EstimateTask]:
    tasks: list[EstimateTask] = []
    for task_name, keywords, task_description in task_hints:
        if any(_contains_keyword(lower_text, keyword) for keyword in keywords):
            tasks.append(
                EstimateTask(
                    name=task_name,
                    engineer_days=0.0,
                    description=task_description,
                )
            )
    if tasks:
        return tasks

    task_name, _keywords, task_description = task_hints[0]
    return [
        EstimateTask(
            name=task_name,
            engineer_days=0.0,
            description=task_description,
        )
    ]


def _contains_keyword(text: str, keyword: str) -> bool:
    if " " in keyword or "/" in keyword:
        return keyword in text
    return re.search(rf"(?<![\w]){re.escape(keyword)}(?![\w])", text) is not None


def _fallback_module_label(search_text: str) -> str:
    first_sentence = re.split(r"[\n\r\.\!\?;]+", search_text, maxsplit=1)[0].strip()
    if 8 <= len(first_sentence) <= 80:
        return first_sentence
    if len(first_sentence) > 80:
        return first_sentence[:77].rstrip() + "..."
    return "General Scope"


def _modules_from_llm_proposal(proposal: AgentStructureProposal) -> list[EstimateModule]:
    modules: list[EstimateModule] = []
    seen_modules: set[str] = set()
    for module in proposal.modules:
        module_name = module.name.strip()
        module_key = module_name.casefold()
        if module_key in seen_modules:
            continue
        seen_modules.add(module_key)
        tasks: list[EstimateTask] = []
        seen_tasks: set[str] = set()
        for task in module.tasks:
            task_name = task.name.strip()
            task_key = task_name.casefold()
            if task_key in seen_tasks:
                continue
            seen_tasks.add(task_key)
            tasks.append(
                EstimateTask(
                    name=task_name,
                    engineer_days=0.0,
                    description=task.description.strip(),
                )
            )
        if tasks:
            modules.append(EstimateModule(name=module_name, engineer_days=0.0, tasks=tasks))
    if not modules:
        raise ValueError("LLM structure proposal did not contain usable modules")
    return modules


async def agent_propose_structure(
    query: EstimationQuery,
    *,
    model: str | None,
    reasoning_effort: str | None,
    persona: str | None,
    llm_service: Any | None = None,
) -> GenerateStageResponse:
    tool_args: dict[str, object] = {
        "model": model,
        "reasoning_effort": reasoning_effort,
        "persona": bool(persona and persona.strip()),
        "source": "llm",
    }
    try:
        if llm_service is None:
            from app.foundation.llm.litellm_service import litellm_router_service

            llm_service = litellm_router_service
        proposal, observable = await llm_service.complete_structured(
            messages=[
                {"role": "system", "content": _STRUCTURE_SYSTEM_PROMPT},
                {"role": "user", "content": _structure_user_prompt(query, persona=persona)},
            ],
            response_model=AgentStructureProposal,
            max_retries=2,
            max_tokens=1_500,
        )
        modules = _modules_from_llm_proposal(proposal)
        reasoning = "Structure proposed dynamically by the LLM from the transcript."
        tool_args.update(
            {
                "modules": len(modules),
                "input_tokens": observable.usage.prompt_tokens,
                "output_tokens": observable.usage.completion_tokens,
            }
        )
    except (LLMServiceError, ValueError, RuntimeError) as exc:
        log.warning("agent_structure_llm_failed_fallback", error=str(exc)[:400])
        modules = _propose_modules(query)
        reasoning = "LLM structure proposal failed; fallback structure proposed from transcript keywords."
        tool_args.update({"source": "fallback", "modules": len(modules), "error_type": type(exc).__name__})

    estimate = RagPipelineEstimate(
        summary=reasoning,
        estimate_markdown=None,
        low_confidence=not bool(modules),
        modules=modules,
        line_items=[],
        assumptions=[],
        sources=[],
    )

    trace = AgentTrace(
        steps=[
            AgentStep(
                step=1,
                reasoning_summary="Propose an editable module->task tree before task-hours grounding.",
                tool="propose_structure",
                tool_args=tool_args,
                observation=f"decomposed into {len(modules)} module(s)",
            )
        ]
    )

    return GenerateStageResponse(estimate=estimate, agent_trace=trace)


async def agent_estimate_task_hours(
    modules: list[TaskHoursModuleInput],
    *,
    retriever: SemanticRetriever,
    top_k: int,
    distance_threshold: float,
    contradiction_threshold: float,
    model: str | None,
    reasoning_effort: str | None,
    max_iterations: int | None,
    persona: str | None,
) -> TaskHoursResult:
    base = await estimate_all(
        modules=modules,
        retriever=retriever,
        top_k=top_k,
        distance_threshold=distance_threshold,
        contradiction_threshold=contradiction_threshold,
    )

    flagged = [estimate for estimate in base.tasks if _should_recover(estimate)]
    if not flagged:
        log.info(
            "agent_hours_phase_completed",
            tasks=len(base.tasks),
            flagged=0,
            recovered=0,
            model=model,
            reasoning_effort=reasoning_effort,
            max_iterations=max_iterations,
            persona=bool(persona and persona.strip()),
        )
        return TaskHoursResult(tasks=base.tasks, agent_trace=AgentTrace())

    max_attempts = max(1, min(int(max_iterations or 2), 3))
    step = 1
    trace_steps: list[AgentStep] = []
    recovered_by_key: dict[tuple[str, str], TaskHoursEstimate] = {}

    for estimate in flagged:
        task_input = _find_task_input(modules, estimate.module, estimate.task)
        if task_input is None:
            continue

        neighbors: list[TaskNeighbor] = []
        retrieval_chunks = []
        for attempt in range(max_attempts):
            retrieval = await _search_task_neighbors(
                retriever=retriever,
                module=estimate.module,
                task=task_input,
                top_k=top_k,
                distance_threshold=distance_threshold,
            )
            retrieval_chunks = retrieval.chunks
            neighbors = _build_neighbor_list(retrieval_chunks, distance_threshold=distance_threshold)
            trace_steps.append(
                AgentStep(
                    step=step,
                    reasoning_summary=(
                        f"Recover hours for task {estimate.module}/{estimate.task}; "
                        f"attempt {attempt + 1}/{max_attempts}."
                    ),
                    tool="search_budgets",
                    tool_args={
                        "query": compose_task_search_text(estimate.module, task_input.name, task_input.description),
                        "top_k": top_k,
                        "distance_threshold": distance_threshold,
                    },
                    observation=f"{len(neighbors)} usable analogs from {len(retrieval_chunks)} retrieved chunks",
                )
            )
            step += 1
            if neighbors:
                break

        if not neighbors:
            continue

        estimated_hours, reliability, dispersion = distance_weighted_consensus(
            [(neighbor.estimated_hours, neighbor.distance) for neighbor in neighbors]
        )
        recovered = estimate.model_copy(
            update={
                "estimated_hours": estimated_hours,
                "reliability": reliability,
                "dispersion": dispersion,
                "has_match": True,
                "hours_range": None,
                "neighbors": neighbors,
            }
        )
        recovered_by_key[(estimate.module, estimate.task)] = recovered
        trace_steps.append(
            AgentStep(
                step=step,
                reasoning_summary="Derive deterministic hours from nearest historical analogs.",
                tool="derive_task_hours",
                tool_args={
                    "module": estimate.module,
                    "task": estimate.task,
                    "neighbors": [neighbor.model_dump() for neighbor in neighbors],
                },
                observation=(
                    f"{estimate.module}/{estimate.task}: {estimated_hours}h "
                    f"(reliability {reliability})"
                ),
            )
        )
        step += 1

    merged: list[TaskHoursEstimate] = []
    for estimate in base.tasks:
        merged.append(recovered_by_key.get((estimate.module, estimate.task), estimate))

    log.info(
        "agent_hours_phase_completed",
        tasks=len(base.tasks),
        flagged=len(flagged),
        recovered=len(recovered_by_key),
        model=model,
        reasoning_effort=reasoning_effort,
        max_iterations=max_iterations,
        persona=bool(persona and persona.strip()),
    )

    return TaskHoursResult(tasks=merged, agent_trace=AgentTrace(steps=trace_steps))
