"""Unit tests for app.services.factory."""
from app.config import settings
from app.services.llm.anthropic import AnthropicLLMService
from app.services.llm.factory import create_llm_service
from app.services.llm.litellm import LiteLLMRouterService
from app.services.llm.openai import OpenAILLMService


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
