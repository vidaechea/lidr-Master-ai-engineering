from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.config import LLMModel
from app.config import settings as _settings

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

def _load_example_transcription(fixture: str | None, fixtures_dir: Path = _FIXTURES_DIR) -> str | None:
    if not fixture:
        return None
    return (fixtures_dir / f"{fixture}_transcription.txt").read_text(encoding="utf-8")

_EXAMPLE_TRANSCRIPTION = _load_example_transcription(_settings.example_fixture)

@dataclass
class EstimationExample:
    """Structured data container for an estimation example."""

    title: str
    meeting_summary: str
    breakdown: list[tuple[str, int, int]]
    total_hours: int
    total_cost: int
    team: list[str]
    duration_weeks: int
    estimation_markdown: str

class ProjectType(str, Enum):
    MOBILE_APP = "mobile_app"
    WEB_SAAS = "web_saas"
    INTERNAL_TOOL = "internal_tool"
    DATA_PIPELINE = "data_pipeline"

class DetailLevel(str, Enum):
    SUMMARY = "summary"
    MEDIUM = "medium"
    DETAILED = "detailed"

class ExampleFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    NARRATIVE = "narrative"

class OutputFormat(str, Enum):
    PHASES_TABLE = "phases_table"
    LINE_ITEMS = "line_items"
    NARRATIVE = "narrative"

class ReferenceProject(BaseModel):
    name: str
    description: str
    total_hours: int | None = None
    total_cost: int | None = None


class ExampleItem(BaseModel):
    title: str
    meeting_summary: str
    estimation_markdown: str

class EstimationRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                **( {"transcription": _EXAMPLE_TRANSCRIPTION} if _EXAMPLE_TRANSCRIPTION else {} ),
                "evaluate": True,
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "top_p": None,
                "top_k": None,
                "reasoning_effort": "medium",
                "max_output_tokens": 2048,
                "pre_call": False,
                "output_format": "phases_table",
                "example_format": "markdown",
                "num_examples": 3,
            }
        }
    )

    transcription: str = Field(
        ...,
        min_length=20,
        description="Meeting transcription or project description to estimate",
    )
    evaluate: bool = Field(
        default=True,
        description="Run the structural evaluation on the generated estimation",
    )
    model: LLMModel | None = Field(
        default=None,
        description="Override the default model for this request",
    )
    temperature: float | None = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (non-reasoning models only)",
    )
    top_p: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Nucleus sampling probability (mutually exclusive with temperature)",
    )
    top_k: int | None = Field(
        default=None,
        ge=1,
        description="Top-K sampling (Anthropic only)",
    )
    reasoning_effort: Literal["low", "medium", "high"] = Field(
        default="medium",
        description="Reasoning effort budget for o-series and Claude thinking models",
    )
    max_output_tokens: int = Field(
        default=2_048,
        ge=256,
        le=32_768,
        description="Maximum tokens the model may generate",
    )
    pre_call: bool = Field(
        default=False,
        description=(
            "When enabled, a first LLM call extracts structured requirements from "
            "the raw transcription before the main estimation call."
        ),
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.PHASES_TABLE,
        description="Desired output structure for the estimation.",
    )
    example_format: ExampleFormat = Field(
        default=ExampleFormat.MARKDOWN,
        description="Format of few-shot examples to include in the system prompt.",
    )
    num_examples: int = Field(
        default=3,
        ge=0,
        le=5,
        description="Number of few-shot examples to include in the system prompt (0–5).",
    )
    project_type: ProjectType | None = Field(
        default=None,
        description="Type of project being estimated. Injected as context before the transcription.",
    )
    detail_level: DetailLevel | None = Field(
        default=None,
        description="Desired level of detail for the estimation output.",
    )
    reference_projects: list[ReferenceProject] | None = Field(
        default=None,
        description="Similar past projects used as context to calibrate the estimation.",
    )

class RequirementCategory(str, Enum):
    FUNCTIONAL = "functional"
    NON_FUNCTIONAL = "non_functional"
    CONSTRAINT = "constraint"
    BUDGET_DEADLINE = "budget_deadline"


class Requirement(BaseModel):
    id: str = Field(description="Unique identifier, e.g. FR-01 for functional, NFR-01 for non-functional")
    description: str = Field(description="Clear, actionable requirement statement")
    category: RequirementCategory


class ExtractedRequirements(BaseModel):
    requirements: list[Requirement]
    open_questions: list[str] = Field(
        default_factory=list,
        description="Ambiguities or open questions that need clarification before estimation",
    )


LOW_CONFIDENCE_THRESHOLD: int = 30
OUT_OF_SCOPE_PREFIX: str = "Out of scope:"


class Phase(BaseModel):
    name: str
    duration_weeks: int
    cost_eur: int
    confidence_pct: int
    summary: str | None = None
    assumptions: list[str] = []

class EstimationResult(BaseModel):
    summary: str
    total_duration_weeks: int
    total_cost_eur: int
    confidence_pct: int
    phases: list[Phase]

    @model_validator(mode='after')
    def validate_phase_costs_sum(self) -> 'EstimationResult':
        total_phases = sum(phase.cost_eur for phase in self.phases)
        if total_phases != self.total_cost_eur:
            raise ValueError(
                f"La suma de los costes de las fases ({total_phases}) no coincide con total_cost_eur ({self.total_cost_eur})"
            )
        return self

class StructureCheck(BaseModel):
    has_title: bool
    has_breakdown_table: bool
    has_totals_section: bool
    has_team_section: bool
    has_duration_section: bool
    declared_total_hours: int | None
    sum_row_hours: int | None
    hours_match: bool | None
    declared_total_cost: float | None
    sum_row_cost: float | None
    cost_match: bool | None
    finish_reason_ok: bool
    score: float
    issues: list[str]


# Backwards-compat alias
EstimationValidation = StructureCheck


# ---------------------------------------------------------------------------
# Tier — product dimension, not authorization
# ---------------------------------------------------------------------------

class UserTier(str, Enum):
    DEVELOPER = "developer"
    PM = "pm"
    EXECUTIVE = "executive"


# ── Per-tier output schemas ──────────────────────────────────────────────────


class TaskDetail(BaseModel):
    """A single implementation task within a phase (developer tier)."""
    name: str
    hours: int
    cost_eur: int
    role: str
    notes: str | None = None


class PhaseDetail(BaseModel):
    """A development phase with granular task breakdown (developer tier)."""
    name: str
    tasks: list[TaskDetail]
    subtotal_hours: int
    subtotal_cost_eur: int
    duration_weeks: int


class DeveloperEstimate(BaseModel):
    """Granular technical breakdown: phases → tasks, hours per role, risks, assumptions."""
    phases: list[PhaseDetail]
    total_hours: int
    total_cost_eur: int
    team_composition: list[str]
    duration_weeks: int
    technical_risks: list[str]
    assumptions: list[str]


class Milestone(BaseModel):
    """A delivery milestone with linked deliverables and dependencies (pm tier)."""
    name: str
    week: int
    deliverables: list[str]
    dependencies: list[str] = []


class PmEstimate(BaseModel):
    """Milestone-oriented: phases, dependencies, resource plan, delivery timeline."""
    phases: list[Phase]
    milestones: list[Milestone]
    total_hours: int
    total_cost_eur: int
    team_by_phase: dict[str, list[str]]
    duration_weeks: int
    dependencies: list[str]
    management_risks: list[str]


class ExecutiveEstimate(BaseModel):
    """Investment summary: total investment, indicative ROI, business risks, go-live."""
    investment_summary: str
    total_cost_eur: int
    duration_weeks: int
    key_deliverables: list[str]
    business_risks: list[str]
    indicative_roi: str | None = None
    recommended_next_step: str | None = None


TierEstimate = Annotated[
    Union[DeveloperEstimate, PmEstimate, ExecutiveEstimate],
    Field(discriminator=None),  # no discriminator — resolved at service layer
]


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    response_id: str
    input_tokens: int
    output_tokens: int
    turn_cost_usd: float
    total_cost_usd: float
    estimated_input_tokens: int
    estimated_precall_cost_usd: float | None
    requirements: str | None
    pre_call_cost_usd: float | None
    validation: StructureCheck | None
    prompt_version: str
    tier: UserTier | None = None
    structured_result: Optional[EstimationResult] = None
    extracted_requirements: Optional[ExtractedRequirements] = None
    tier_result: Optional[Union[DeveloperEstimate, PmEstimate, ExecutiveEstimate]] = None