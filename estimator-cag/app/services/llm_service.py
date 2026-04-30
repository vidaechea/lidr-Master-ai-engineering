from typing import Any, Optional

from app.config import settings
from app.services.base_llm_service import BaseLLMService
from app.services.openai_llm_service import (
    DEFAULT_MODEL,
    MODELS,
    OpenAILLMService,
    _MSG_OVERHEAD,
    _PRIMING_TOKENS,
)

# --------------------------------------------------------------------------- #
# Active service — selected via LLM_PROVIDER env var
# --------------------------------------------------------------------------- #

def _build_service() -> BaseLLMService:
    provider = settings.llm_provider.lower()
    if provider == "anthropic":
        from app.services.anthropic_llm_service import AnthropicLLMService
        return AnthropicLLMService()
    return OpenAILLMService()


_active_service: BaseLLMService = _build_service()

# Expose the OpenAI singleton under the legacy name so existing tests that
# reference ``svc._openai_service`` continue to work.
_openai_service: OpenAILLMService = (
    _active_service
    if isinstance(_active_service, OpenAILLMService)
    else OpenAILLMService()
)

# --------------------------------------------------------------------------- #
# Backward-compatible public API
# --------------------------------------------------------------------------- #

def estimate_call_tokens(
    system_prompt: str,
    user_message: str,
    model: str = DEFAULT_MODEL,
) -> int:
    """Return the estimated number of input tokens for a system+user call."""
    return _active_service._count_tokens(system_prompt, user_message, model)


async def estimate(
    transcription: str,
    *,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    top_k: Optional[int] = None,
    reasoning_effort: str = "medium",
    verbosity: str = "low",
    max_output_tokens: int = 2_048,
    continue_conversation: bool = False,
) -> dict[str, Any]:
    """Generate a software effort estimate from a meeting transcription."""
    return await _active_service.estimate(
        transcription,
        model=model,
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        max_output_tokens=max_output_tokens,
        continue_conversation=continue_conversation,
    )


def reset() -> None:
    """Reset the active service's multi-turn session state."""
    _active_service.reset()
