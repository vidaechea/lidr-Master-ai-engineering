import structlog

from app.config import settings
from app.services.base_llm_service import BaseLLMService

log = structlog.get_logger(__name__)


def create_llm_service() -> BaseLLMService:
    """Return a concrete LLM service instance for the configured provider.

    This is the single place in the codebase that knows which provider is
    active.  Adding a new provider only requires a new branch here.
    """
    provider = settings.llm_provider

    if provider == "anthropic":
        from app.services.anthropic_llm_service import AnthropicLLMService

        log.info("llm_service_created", provider=provider, model=settings.llm_model)
        return AnthropicLLMService()

    from app.services.openai_llm_service import OpenAILLMService

    log.info("llm_service_created", provider=provider, model=settings.llm_model)
    return OpenAILLMService()
