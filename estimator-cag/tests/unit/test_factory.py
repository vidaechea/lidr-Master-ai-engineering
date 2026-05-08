"""Unit tests for app.services.factory."""
from app.config import settings
from app.services.anthropic_llm_service import AnthropicLLMService
from app.services.factory import create_llm_service
from app.services.litellm_router_service import LiteLLMRouterService
from app.services.openai_llm_service import OpenAILLMService


def test_create_llm_service_returns_openai(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "openai")
    service = create_llm_service()
    assert isinstance(service, OpenAILLMService)


def test_create_llm_service_returns_anthropic(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    service = create_llm_service()
    assert isinstance(service, AnthropicLLMService)


def test_create_llm_service_returns_litellm_router(monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "litellm")
    service = create_llm_service()
    assert isinstance(service, LiteLLMRouterService)
