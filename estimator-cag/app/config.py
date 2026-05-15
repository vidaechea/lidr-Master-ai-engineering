from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class ModelConfig:
    """Static metadata for a single model in the registry."""

    litellm_model: str       # model string passed to LiteLLM (e.g. "anthropic/claude-sonnet-4-6")
    input_price: float       # USD per 1 million input tokens
    output_price: float      # USD per 1 million output tokens
    context_window: int      # maximum context length in tokens
    provider: str            # "openai" | "anthropic"
    reasoning: bool = field(default=False)  # True for o-series / Claude thinking models


# ---------------------------------------------------------------------------
# Model registry — single source of truth for all supported models
# ---------------------------------------------------------------------------

MODEL_REGISTRY: dict[str, ModelConfig] = {
    # OpenAI
    "gpt-4o-mini":          ModelConfig("gpt-4o-mini",          0.15,  0.60, 128_000, "openai"),
    "gpt-5.4-mini":         ModelConfig("gpt-5.4-mini",         0.75,  4.50, 128_000, "openai"),
    "gpt-5.4":              ModelConfig("gpt-5.4",              2.50, 15.00, 128_000, "openai"),
    "gpt-4-turbo":          ModelConfig("gpt-4-turbo",         10.00, 30.00, 128_000, "openai"),
    "gpt-3.5-turbo":        ModelConfig("gpt-3.5-turbo",        0.50,  1.50,  16_385, "openai"),
    "o3-mini":              ModelConfig("o3-mini",               1.10,  4.40, 200_000, "openai", reasoning=True),
    "o3":                   ModelConfig("o3",                   10.00, 40.00, 200_000, "openai", reasoning=True),
    "o4-mini":              ModelConfig("o4-mini",               1.10,  4.40, 200_000, "openai", reasoning=True),
    "o4-mini-2025-04-16":   ModelConfig("o4-mini-2025-04-16",   1.10,  4.40, 200_000, "openai", reasoning=True),
    # Anthropic — litellm_model must include the "anthropic/" prefix
    "claude-haiku-4-5-20251001": ModelConfig("anthropic/claude-haiku-4-5-20251001",  1.00,  5.00, 200_000, "anthropic"),
    "claude-sonnet-4-6":         ModelConfig("anthropic/claude-sonnet-4-6",          3.00, 15.00, 200_000, "anthropic"),
    "claude-opus-4-7":           ModelConfig("anthropic/claude-opus-4-7",           15.00, 75.00, 200_000, "anthropic", reasoning=True),
}

LLMModel = Literal[
    # OpenAI
    "gpt-3.5-turbo",
    "gpt-4-turbo",
    "gpt-4o-mini",
    "gpt-5.4-mini",
    "gpt-5.4",
    "o3-mini",
    "o3",
    "o4-mini",
    "o4-mini-2025-04-16",
    # Anthropic
    "claude-haiku-4-5-20251001",
    "claude-sonnet-4-6",
    "claude-opus-4-7",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    llm_model: LLMModel = "gpt-4o-mini"
    llm_provider: str = "openai"
    app_env: str = "development"
    log_level: str = "DEBUG"
    example_fixture: Optional[Literal["short", "long"]] = None

    # Cache — exact match (layer 1)
    cache_enabled: bool = False
    redis_url: str = "redis://localhost:6379"
    cache_ttl: int = 86400  # 24 hours

    # Cache — semantic similarity (layer 2, requires Redis Stack + redisvl)
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = 0.92
    semantic_cache_log_only: bool = False

    # Prompt version
    prompt_version: str = "v1"

    # LiteLLM Router resilience
    router_num_retries: int = 2
    router_timeout: int = 60
    router_retry_after: int = 5
    router_allowed_fails: int = 3
    router_cooldown_time: int = 30

    # LiteLLM Router — primary and fallback model names
    litellm_primary_model: str = "gpt-4o-mini"
    litellm_fallback_model: str = "anthropic/claude-haiku-4-5-20251001"

    # Internal service auth — set to require X-Internal-API-Key on all /api/* routes.
    # Leave empty in local development to allow open access.
    internal_api_key: Optional[str] = None


settings = Settings()

# ---------------------------------------------------------------------------
# LiteLLM Router — model list with primary + fallback
# ---------------------------------------------------------------------------

LOGICAL_MODEL = "default"
_FALLBACK_MODEL = "fallback"


def build_model_list(primary_model: str | None = None, fallback_model: str | None = None) -> list[dict]:
    """Build the LiteLLM Router model_list from the given primary/fallback models.

    Falls back to ``settings.litellm_primary_model`` / ``settings.litellm_fallback_model``
    when arguments are not provided.
    """
    primary = primary_model or settings.litellm_primary_model
    fallback = fallback_model or settings.litellm_fallback_model

    # Resolve API key: Anthropic models use the anthropic key, all others use OpenAI key.
    def _api_key(model: str) -> str | None:
        return settings.anthropic_api_key if model.startswith("anthropic/") else settings.openai_api_key

    return [
        {
            "model_name": LOGICAL_MODEL,
            "litellm_params": {"model": primary, "api_key": _api_key(primary)},
        },
        {
            "model_name": _FALLBACK_MODEL,
            "litellm_params": {"model": fallback, "api_key": _api_key(fallback)},
        },
    ]


model_list = build_model_list()
