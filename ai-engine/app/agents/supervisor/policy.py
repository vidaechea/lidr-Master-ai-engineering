from __future__ import annotations

from typing import Literal

from app.config import settings

SUPERVISOR_ORDER: tuple[str, ...] = (
    "requirements_extractor",
    "budget_searcher",
    "estimate_generator",
    "coherence_validator",
)

SUPERVISOR_SYSTEM_PROMPT = """You are the supervisor of a software estimation graph.
Choose one next agent that can make progress with current state.

Available agents:
- requirements_extractor: requires transcript, produces requirements/components.
- budget_searcher: requires components, produces budget matches.
- estimate_generator: requires components and completed budget search, produces estimate.
- coherence_validator: requires estimate, produces validation and confidence.
- finish: choose only when no worker should run and estimate is ready for closing.

Rules:
- Never route to an agent whose inputs are missing.
- Never route to an agent that already ran.
- Return only one next agent and a short reason.
"""


def summarize_state_for_router(state: dict[str, object]) -> str:
    components = list(state.get("components") or [])
    component_hits = dict(state.get("component_hits") or {})
    grounded = sum(1 for hits in component_hits.values() if hits)
    routed = ", ".join(row["next_agent"] for row in state.get("routing_history") or []) or "none"
    return "\n".join(
        [
            "Current estimation state:",
            f"- transcription_len: {len(state.get('transcription') or '')}",
            f"- requirements: {len(state.get('requirements') or [])}",
            f"- components: {len(components)}",
            f"- grounded_components: {grounded}/{len(components) if components else 0}",
            f"- has_estimate: {'yes' if state.get('structured_estimate') else 'no'}",
            f"- has_validation: {'yes' if state.get('validation') else 'no'}",
            f"- already_routed: {routed}",
            "Choose next_agent.",
        ]
    )


def already_ran(agent: str, state: dict[str, object]) -> bool:
    return any(record.get("next_agent") == agent for record in (state.get("routing_history") or []))


def inputs_ready(agent: str, state: dict[str, object]) -> bool:
    if agent == "requirements_extractor":
        return bool(state.get("transcription"))
    if agent == "budget_searcher":
        return bool(state.get("components"))
    if agent == "estimate_generator":
        return bool(state.get("components")) and already_ran("budget_searcher", state)
    if agent == "coherence_validator":
        return bool(state.get("structured_estimate"))
    return False


def is_legal(target: str, state: dict[str, object]) -> bool:
    if target == "finish":
        return True
    if target not in SUPERVISOR_ORDER:
        return False
    return inputs_ready(target, state) and not already_ran(target, state)


def fallback_next(state: dict[str, object]) -> str:
    for candidate in SUPERVISOR_ORDER:
        if is_legal(candidate, state):
            return candidate
    return "finish"


def review_reasons(state: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    confidence = state.get("confidence")
    if confidence is not None and float(confidence) < settings.agentic_estimation_confidence_threshold:
        reasons.append(
            f"confidence {float(confidence):.2f} is below threshold {settings.agentic_estimation_confidence_threshold:.2f}"
        )
    validation = state.get("validation") or {}
    if isinstance(validation, dict) and validation.get("outside_historical_range"):
        reasons.append("at least one component is outside historical range")
    if isinstance(validation, dict) and validation.get("no_historical_precedent"):
        reasons.append("estimate has no historical precedent")

    components_count = len(state.get("components") or [])
    grounded_count = 0
    component_hits = state.get("component_hits") or {}
    if isinstance(component_hits, dict):
        for hits in component_hits.values():
            if hits:
                grounded_count += 1
    if components_count and (grounded_count / components_count) < settings.agentic_supervisor_min_grounded_ratio:
        reasons.append(
            f"grounded ratio {grounded_count}/{components_count} is below {settings.agentic_supervisor_min_grounded_ratio:.2f}"
        )
    return reasons


def requires_human_review(state: dict[str, object]) -> bool:
    if state.get("confidence") is not None and float(state["confidence"]) < settings.agentic_estimation_confidence_threshold:
        return True
    components_count = len(state.get("components") or [])
    grounded_count = 0
    component_hits = state.get("component_hits") or {}
    if isinstance(component_hits, dict):
        for hits in component_hits.values():
            if hits:
                grounded_count += 1
    if components_count and (grounded_count / components_count) < settings.agentic_supervisor_min_grounded_ratio:
        return True
    validation = state.get("validation") or {}
    if not isinstance(validation, dict):
        return False
    return bool(validation.get("no_historical_precedent") or validation.get("outside_historical_range"))


def route_target_for_finish(state: dict[str, object]) -> Literal["human_review_gate", "finalize"]:
    if requires_human_review(state) and not state.get("human_decision"):
        return "human_review_gate"
    return "finalize"