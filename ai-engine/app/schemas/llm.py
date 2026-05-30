from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LLMUsage(BaseModel):
    """Token usage statistics from an LLM completion."""

    prompt_tokens: int = Field(
        description="Number of tokens consumed from the input prompt."
    )
    completion_tokens: int = Field(
        description="Number of tokens generated in the completion."
    )
    total_tokens: int = Field(
        description="Total tokens consumed (prompt + completion)."
    )


class LLMObservableResponse(BaseModel):
    """Structured wrapper for LLM response with explicit observability properties."""

    model_config = ConfigDict(json_encoders={Decimal: float})

    model: str = Field(
        description="The actual model that was used for this completion."
    )
    content: str | None = Field(
        default=None,
        description="The text content of the completion (for non-streaming responses).",
    )
    usage: LLMUsage = Field(
        description="Token usage statistics."
    )
    latency_ms: float = Field(
        description="Time elapsed for the completion in milliseconds."
    )
    cost_usd: Decimal = Field(
        description="Estimated cost in USD for this completion."
    )
    response_id: str | None = Field(
        default=None,
        description="Provider-specific response ID for tracing.",
    )
    raw_response: object = Field(
        default=None,
        description="Raw response object from the provider for advanced use cases.",
    )
