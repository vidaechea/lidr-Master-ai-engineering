from __future__ import annotations

import json
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.domain.schemas.estimation import CriticFeedback, EstimationExample, EstimationRequest, ExampleFormat, UserTier
from app.generation.conversation.sessions import ProjectMetadata

log = structlog.get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent
_ENV = Environment(
	loader=FileSystemLoader(_PROMPTS_DIR),
	undefined=StrictUndefined,
	trim_blocks=True,
	lstrip_blocks=True,
)

_EXAMPLES_CACHE: dict[str, list[EstimationExample]] = {}


def _load_examples_from_template(template_dir: str) -> list[EstimationExample]:
	"""Load estimation examples from examples_data.json at estimation/{template_dir}/."""
	if template_dir in _EXAMPLES_CACHE:
		return _EXAMPLES_CACHE[template_dir]

	template_path = f"estimation/{template_dir}/examples_data.json"
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
		_EXAMPLES_CACHE[template_dir] = examples
		log.debug("examples_loaded_from_template", template_dir=template_dir, count=len(examples))
		return examples
	except Exception as exc:  # noqa: BLE001
		log.error("failed_to_load_examples_from_template", template_dir=template_dir, error=str(exc))
		return []


def get_examples(version: str = "v1", tier: str | None = None) -> list[EstimationExample]:
	"""Get estimation examples for a given tier and version."""
	resolved_tier = tier or "developer"
	return _load_examples_from_template(f"{resolved_tier}/{version}")


def format_examples_for_prompt(
	examples: list[EstimationExample],
	fmt: ExampleFormat = ExampleFormat.MARKDOWN,
) -> str:
	"""Format examples for inclusion in a prompt."""
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
				f"Example {i} - {ex.title}. "
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
	tier: UserTier | None = None,
	project_metadata: ProjectMetadata | None = None,
) -> tuple[str, str]:
	"""Render the system and user prompts for an estimation request."""
	if tier is not None:
		template_root = f"estimation/{tier.value}/{version}"
		examples_key = f"{tier.value}/{version}"
	else:
		template_root = f"estimation/developer/{version}"
		examples_key = f"developer/{version}"

	system_template = _ENV.get_template(f"{template_root}/system.j2")
	user_template = _ENV.get_template(f"{template_root}/user.j2")

	examples = _load_examples_from_template(examples_key)
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
		"project_metadata": project_metadata or ProjectMetadata(),
	}

	system_prompt = system_template.render(**context).strip()
	user_prompt = user_template.render(**context).strip()

	log.debug(
		"prompts_rendered",
		version=version,
		tier=tier.value if tier else None,
		system_prompt_len=len(system_prompt),
		user_prompt_len=len(user_prompt),
	)

	return system_prompt, user_prompt


def render_requirements_extraction_prompt(transcription: str, version: str = "v1") -> tuple[str, str]:
	"""Render the system and user prompts for requirements extraction."""
	template_root = f"requirements_extraction/{version}"
	system_template = _ENV.get_template(f"{template_root}/system.j2")
	user_template = _ENV.get_template(f"{template_root}/user.j2")

	context = {"transcription": transcription}

	system_prompt = system_template.render(**context).strip()
	user_prompt = user_template.render(**context).strip()
	return system_prompt, user_prompt


render_pre_call_prompt = render_requirements_extraction_prompt


def render_critic_prompt(
	candidate_estimate: str,
	request: EstimationRequest,
	project_metadata: ProjectMetadata | None = None,
) -> tuple[str, str]:
	"""Render the system and user prompts for the Critic role."""
	system_template = _ENV.get_template("acb/critic/system.j2")
	user_template = _ENV.get_template("acb/critic/user.j2")

	context = {
		"candidate_estimate": candidate_estimate,
		"project_description": request.transcription,
		"project_metadata": project_metadata or ProjectMetadata(),
	}

	return system_template.render(**context).strip(), user_template.render(**context).strip()


def render_boss_prompt(
	candidate_estimate: str,
	critic_feedback: CriticFeedback,
	iteration: int,
	max_iterations: int,
	project_metadata: ProjectMetadata | None = None,
) -> tuple[str, str]:
	"""Render the system and user prompts for the Boss role."""
	system_template = _ENV.get_template("acb/boss/system.j2")
	user_template = _ENV.get_template("acb/boss/user.j2")

	context = {
		"candidate_estimate": candidate_estimate,
		"critic_feedback": critic_feedback,
		"iteration": iteration,
		"max_iterations": max_iterations,
		"project_metadata": project_metadata or ProjectMetadata(),
	}

	return system_template.render(**context).strip(), user_template.render(**context).strip()


