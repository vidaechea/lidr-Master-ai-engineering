import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Synchronous test client for integration tests."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def force_openai_provider():
    """Force OpenAI as the active facade provider for all tests.

    Prevents tests from hitting real provider APIs when LLM_PROVIDER is
    set to a non-OpenAI value in the local .env file.
    The OpenAI service singleton state is also reset so tests are isolated.
    """
    import app.services.llm_service as svc
    import app.services.openai_llm_service as openai_svc

    original = svc._active_service
    svc._active_service = svc._openai_service
    openai_svc._client = None
    svc._openai_service._last_response_id = None
    svc._openai_service._turn_count = 0
    svc._openai_service._total_cost = 0.0
    yield
    svc._active_service = original
