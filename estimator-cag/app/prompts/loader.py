from __future__ import annotations

import json
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.schemas.estimation import EstimationExample, EstimationRequest, ExampleFormat

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent
_ENV = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)

_EXAMPLES_CACHE: dict[str, list[EstimationExample]] = {}


def _load_examples_from_template(version: str = "v1") -> list[EstimationExample]:
    """Load estimation examples from the examples_data.json template."""
    if version in _EXAMPLES_CACHE:
        return _EXAMPLES_CACHE[version]
    
    template_path = f"estimation/{version}/examples_data.json"
    try:
        template = _ENV.get_template(template_path)
        json_data = template.render()
        data = json.loads(json_data)
        
        examples = [
            EstimationExample(
                title=ex["title"],
                meeting_summary=ex["meeting_summary"],
                breakdown=[(task["task"], task["hours"], task["cost_eur"]) for task in ex["breakdown"]],
                total_hours=ex["total_hours"],
                total_cost=ex["total_cost_eur"],
                team=ex["team"],
                duration_weeks=ex["duration_weeks"],
                estimation_markdown=ex["estimation_markdown"],
            )
            for ex in data
        ]
        _EXAMPLES_CACHE[version] = examples
        log.debug("examples_loaded_from_template", version=version, count=len(examples))
        return examples
    except Exception as e:
        log.error("failed_to_load_examples_from_template", version=version, error=str(e))
        return []


def get_examples(version: str = "v1") -> list[EstimationExample]:
    """Get estimation examples for a given template version."""
    return _load_examples_from_template(version)


def format_examples_for_prompt(
    examples: list[EstimationExample],
    fmt: ExampleFormat = ExampleFormat.MARKDOWN,
) -> str:
    """Format examples for inclusion in a prompt.
    
    Args:
        examples: List of EstimationExample objects.
        fmt: Format to use (MARKDOWN, JSON, or NARRATIVE).
    
    Returns:
        Formatted string representation of examples.
    """
    if fmt == ExampleFormat.MARKDOWN:
        blocks: list[str] = []
        for i, ex in enumerate(examples, start=1):
            block = (
                f"--- Example {i} ---\n"
                f"Meeting summary:\n{ex.meeting_summary}\n\n"
                f"Generated estimation:\n{ex.estimation_markdown.strip()}"
            )
            blocks.append(block)
        return "\n\n".join(blocks)

    if fmt == ExampleFormat.JSON:
        payload = [
            {
                "index": i,
                "title": ex.title,
                "meeting_summary": ex.meeting_summary,
                "breakdown": [
                    {"task": task, "hours": hours, "cost_eur": cost}
                    for task, hours, cost in ex.breakdown
                ],
                "total_hours": ex.total_hours,
                "total_cost_eur": ex.total_cost,
                "team": ex.team,
                "duration_weeks": ex.duration_weeks,
            }
            for i, ex in enumerate(examples, start=1)
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    if fmt == ExampleFormat.NARRATIVE:
        blocks: list[str] = []
        for i, ex in enumerate(examples, start=1):
            team_str = ", ".join(ex.team)
            tasks_str = "; ".join(
                f"{task} ({hours}h, {cost} EUR)"
                for task, hours, cost in ex.breakdown
            )
            block = (
                f"Example {i} — {ex.title}. "
                f"Client request: {ex.meeting_summary} "
                f"The work was broken down as follows: {tasks_str}. "
                f"Total effort: {ex.total_hours} hours over {ex.duration_weeks} weeks, "
                f"costing {ex.total_cost} EUR. "
                f"Recommended team: {team_str}."
            )
            blocks.append(block)
        return "\n\n".join(blocks)

    raise ValueError(f"Unsupported example format: {fmt}")


def render_estimation_prompt(
    request: EstimationRequest,
    version: str = "v1",
) -> tuple[str, str]:
    """Render the system and user prompts for an estimation request.
    
    Args:
        request: EstimationRequest with transcription, output_format, detail_level, etc.
        version: Template version (default "v1").
    
    Returns:
        Tuple of (system_prompt, user_prompt) ready to send to the model.
    """
    template_root = f"estimation/{version}"
    system_template = _ENV.get_template(f"{template_root}/system.j2")
    user_template = _ENV.get_template(f"{template_root}/user.j2")

    examples = get_examples(version)
    selected_examples = examples[: request.num_examples]
    formatted_examples = format_examples_for_prompt(selected_examples, fmt=request.example_format)

    context = {
        "output_format": request.output_format.value,
        "detail_level": request.detail_level.value if request.detail_level else None,
        "project_description": request.transcription,
        "project_type": request.project_type.value if request.project_type else None,
        "num_examples": request.num_examples,
        "examples": formatted_examples,
        "reference_projects": request.reference_projects,
    }

    system_prompt = system_template.render(**context).strip()
    user_prompt = user_template.render(**context).strip()
    
    log.debug(
        "prompts_rendered",
        version=version,
        system_prompt_len=len(system_prompt),
        user_prompt_len=len(user_prompt),
    )
    
    return system_prompt, user_prompt


def render_requirements_extraction_prompt(transcription: str, version: str = "v1") -> tuple[str, str]:
    """Render the system and user prompts for requirements extraction from transcription."""
    template_root = f"requirements_extraction/{version}"
    system_template = _ENV.get_template(f"{template_root}/system.j2")
    user_template = _ENV.get_template(f"{template_root}/user.j2")

    context = {"transcription": transcription}

    system_prompt = system_template.render(**context).strip()
    user_prompt = user_template.render(**context).strip()
    return system_prompt, user_prompt


# Deprecated alias for backward compatibility
render_pre_call_prompt = render_requirements_extraction_prompt
