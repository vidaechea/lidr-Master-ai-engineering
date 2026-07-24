from __future__ import annotations

from collections.abc import Callable, Mapping

from app.agents.supervisor.policy import requires_human_review, review_reasons
from app.config import settings


def build_human_review_interrupt_payload(state: Mapping[str, object]) -> dict[str, object]:
    return {
        "reason": "low_confidence_estimate",
        "estimation_id": state.get("estimation_id"),
        "reasons": review_reasons(dict(state)),
        "estimate": state.get("structured_estimate"),
        "confidence": state.get("confidence"),
        "validation": state.get("validation", {}),
        "threshold": settings.agentic_estimation_confidence_threshold,
    }


def build_human_decision_update(
    *,
    state: Mapping[str, object],
    decision: object,
    digest_payload: Callable[[dict[str, object]], str],
) -> dict[str, object]:
    decision_dict = decision if isinstance(decision, dict) else {}
    decision_label = str(decision_dict.get("decision") or decision_dict.get("action") or "approve")
    return {
        "human_decision": decision,
        "trace": [
            {
                "reasoning": "A persisted human decision was received after the low-confidence interrupt.",
                "action": "human_review_gate.resume",
                "observation": "Human decision folded into graph state.",
            }
        ],
        "agent_contributions": [
            {
                "step": int(state.get("supervisor_steps") or 0),
                "agent": "human",
                "action": "review_decision",
                "tool": None,
                "outcome": "ok",
                "summary": f"Human decision: {decision_label}",
                "args_digest": digest_payload(decision_dict),
                "duration_ms": None,
            }
        ],
    }


def build_finalize_update_payload(
    *,
    state: Mapping[str, object],
    decision: Mapping[str, object],
) -> dict[str, object]:
    update_payload: dict[str, object] = {}

    action = str(decision.get("action") or decision.get("decision") or "approve")
    overrides = decision.get("estimate_overrides")
    if isinstance(overrides, dict):
        update_payload.update(overrides)

    if action == "reject":
        update_payload["status"] = "needs_review"
    elif decision:
        update_payload["status"] = "validated"
    elif requires_human_review(dict(state)) and not decision:
        update_payload["status"] = "awaiting_human_review"
    else:
        update_payload["status"] = "validated" if not state.get("validation_errors") else "needs_review"

    if state.get("confidence") is not None:
        update_payload["confidence"] = state["confidence"]
    if state.get("validation"):
        update_payload["validation"] = state["validation"]

    return update_payload
