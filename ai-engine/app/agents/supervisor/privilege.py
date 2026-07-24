from __future__ import annotations

from typing import TypedDict

import structlog

from app.config import settings

log = structlog.get_logger(__name__)

AGENT_ALLOWED_TOOLS: dict[str, set[str]] = {
    "requirements_extractor": set(),
    "budget_searcher": {"search_budgets"},
    "estimate_generator": {"calculate_estimate"},
    "coherence_validator": {"validate_estimate"},
    "supervisor": set(),
}


class ToolValidationContribution(TypedDict):
    step: int
    agent: str
    action: str
    tool: str | None
    outcome: str
    summary: str
    args_digest: str | None
    duration_ms: int | None


def validate_action(
    *,
    agent: str,
    tool: str,
    step: int,
) -> tuple[bool, ToolValidationContribution]:
    allowed = AGENT_ALLOWED_TOOLS.get(agent, set())
    if tool in allowed:
        log.info("agent_tool_allowed", agent=agent, tool=tool)
        return True, {
            "step": step,
            "agent": agent,
            "action": f"tool:{tool}",
            "tool": tool,
            "outcome": "ok",
            "summary": "allowed",
            "args_digest": None,
            "duration_ms": None,
        }

    message = f"Agent '{agent}' cannot use tool '{tool}'. Allowed={sorted(allowed)}"
    log.error("agent_tool_rejected", agent=agent, tool=tool, allowed=sorted(allowed))
    contribution: ToolValidationContribution = {
        "step": step,
        "agent": agent,
        "action": f"tool:{tool}",
        "tool": tool,
        "outcome": "denied",
        "summary": message,
        "args_digest": None,
        "duration_ms": None,
    }
    if settings.agentic_supervisor_privilege_strict:
        raise PermissionError(message)
    return False, contribution