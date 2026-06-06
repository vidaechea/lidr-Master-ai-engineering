from __future__ import annotations

from app.domain.schemas.estimation import EstimationResult, ExtractedRequirements


def format_requirements_text(extracted: ExtractedRequirements) -> str:
    lines = [f"[{r.id}] ({r.category.value}) {r.description}" for r in extracted.requirements]
    if extracted.open_questions:
        lines.append("\nOpen questions:")
        lines.extend(f"  - {q}" for q in extracted.open_questions)
    return "\n".join(lines)


def render_estimation_markdown(result: EstimationResult) -> str:
    lines = [
        f"## {result.summary}",
        "",
        (
            f"**Confidence:** {result.confidence_pct}%  |  "
            f"**Duration:** {result.total_duration_weeks} weeks  |  "
            f"**Total cost:** {result.total_cost_eur:,} EUR"
        ),
        "",
        "| Phase | Duration (weeks) | Cost (EUR) | Confidence |",
        "|-------|-----------------|------------|------------|",
    ]
    for phase in result.phases:
        lines.append(
            f"| {phase.name} | {phase.duration_weeks} | {phase.cost_eur:,} | {phase.confidence_pct}% |"
        )
    for phase in result.phases:
        if phase.assumptions:
            lines.extend(["", f"**{phase.name}** assumptions:"])
            lines.extend(f"- {a}" for a in phase.assumptions)
    lines.extend(["", f"**Total cost:** {result.total_cost_eur:,} EUR"])
    return "\n".join(lines)
