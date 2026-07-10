from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


class AgentStep(BaseModel):
    """One reason->act->observe step emitted by the agent flow."""

    step: int = Field(ge=1)
    reasoning_summary: str | None = Field(default=None)
    tool: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    observation: str


class AgentTrace(BaseModel):
    """Ordered audit trail for agent decisions and tool actions."""

    steps: list[AgentStep] = Field(default_factory=list)

    def render(self) -> str:
        if not self.steps:
            return "(no tool steps - the agent answered without calling tools)"
        lines: list[str] = []
        for step in self.steps:
            reasoning = step.reasoning_summary or "(no reasoning summary emitted)"
            tool_args = _CONTROL_CHARS.sub(
                "",
                json.dumps(step.tool_args, ensure_ascii=False, default=str),
            )
            lines.append(
                "\n".join(
                    [
                        f"STEP {step.step}",
                        f"  reasoning:   {reasoning}",
                        f"  action:      {step.tool}({tool_args})",
                        f"  observation: {step.observation}",
                    ]
                )
            )
        return "\n\n".join(lines)
