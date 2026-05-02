from enum import Enum
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.config import LLMModel

from app.config import settings as _settings

_FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


def _load_example_transcription(fixture: str | None, fixtures_dir: Path = _FIXTURES_DIR) -> str | None:
    if not fixture:
        return None
    return (fixtures_dir / f"{fixture}_transcription.txt").read_text(encoding="utf-8")


_EXAMPLE_TRANSCRIPTION = _load_example_transcription(_settings.example_fixture)

class ExampleFormat(str, Enum):
    MARKDOWN = "markdown"
    JSON = "json"
    NARRATIVE = "narrative"


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
            }
        }
    )

    transcription: str = Field(
        ...,
        min_length=50,
        description="Meeting transcription text to estimate",
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
    example_format: ExampleFormat = Field(
        default=ExampleFormat.MARKDOWN,
        description=(
            "Format used for the few-shot examples in the system prompt. "
            "Controls the output style: 'markdown' (table-based), 'json' (structured JSON), "
            "or 'narrative' (plain text prose)."
        ),
    )


class StructureCheck(BaseModel):
    """Level-1 structural evaluation of the generated estimation."""

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


class EstimationResponse(BaseModel):
    estimation: str
    model: str
    input_tokens: int
    output_tokens: int
    reasoning_tokens: Optional[int]
    turn_cost_usd: float
    total_cost_usd: float
    response_id: str
    estimated_input_tokens: int
    estimated_precall_cost_usd: float
    validation: StructureCheck | None = None
    requirements: str | None = None
    pre_call_cost_usd: float | None = None