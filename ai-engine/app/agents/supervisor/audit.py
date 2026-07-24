from __future__ import annotations

from collections.abc import Callable
from typing import Literal


def build_route_audit_update(
    *,
    goto: str,
    reason: str,
    step: int,
    source: Literal["llm", "fallback", "limit"],
    confidence: Literal["low", "medium", "high"] | None,
    digest_payload: Callable[[dict[str, object]], str],
) -> dict[str, object]:
    return {
        "supervisor_steps": step + 1,
        "routing_history": [
            {
                "step": step,
                "next_agent": "finish" if goto in {"human_review_gate", "finalize"} else goto,
                "reason": reason,
                "source": source,
                "decision_confidence": confidence,
            }
        ],
        "agent_contributions": [
            {
                "step": step,
                "agent": "supervisor",
                "action": "route",
                "tool": None,
                "outcome": "ok",
                "summary": f"Routed to {goto} ({source}).",
                "args_digest": digest_payload({"goto": goto, "source": source}),
                "duration_ms": None,
            }
        ],
        "trace": [
            {
                "reasoning": reason,
                "action": f"supervisor.route.{goto}",
                "observation": f"Supervisor routed to {goto}.",
            }
        ],
    }
