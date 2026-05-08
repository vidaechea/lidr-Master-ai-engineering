import structlog

from app.config import settings
from app.services.base_llm_service import BaseLLMService

log = structlog.get_logger(__name__)

_PROVIDER_REGISTRY: dict[str, str] = {
    "openai": "app.services.openai_llm_service.OpenAILLMService",
    "anthropic": "app.services.anthropic_llm_service.AnthropicLLMService",
    "litellm": "app.services.litellm_router_service.LiteLLMRouterService",
}


def _load_service_class(dotted_path: str) -> type[BaseLLMService]:
    module_path, class_name = dotted_path.rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def create_llm_service() -> BaseLLMService:
    """Return a concrete LLM service instance for the configured provider.

    Raises ValueError for any provider not present in _PROVIDER_REGISTRY.
    To add a new provider, register it in _PROVIDER_REGISTRY — no branching needed.
    If cache_enabled is True, wraps the service with CachedLLMService.
    """
    provider = settings.llm_provider

    if provider not in _PROVIDER_REGISTRY:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Registered providers: {sorted(_PROVIDER_REGISTRY)}"
        )

    service_class = _load_service_class(_PROVIDER_REGISTRY[provider])
    service: BaseLLMService = service_class()
    log.info("llm_service_created", provider=provider)

    if settings.cache_enabled:
        from app.services.cache_service import CachedLLMService
        service = CachedLLMService(inner=service)
        log.info("cache_enabled", redis_url=settings.redis_url, ttl=settings.cache_ttl)

    return service
