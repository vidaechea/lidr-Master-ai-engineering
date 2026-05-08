import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Synchronous test client for integration tests."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def force_openai_provider(monkeypatch):
    """Force OpenAI as the active provider for all tests.

    Patches settings.llm_provider so that create_llm_service() always
    returns an OpenAILLMService regardless of the local .env value.
    Also resets the lazy AsyncOpenAI client so tests remain isolated.
    Disables cache so the factory returns raw service instances.
    """
    import app.services.openai_llm_service as openai_svc
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "cache_enabled", False)
    openai_svc._client = None
    yield
    openai_svc._client = None
