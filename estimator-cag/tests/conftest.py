import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.estimations import get_llm_service
from app.services.openai_llm_service import _openai_service


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Synchronous test client for integration tests.

    Always injects the OpenAI service singleton so that:
    - patch("app.services.openai_llm_service._get_client") intercepts real API calls.
    - patch.object(svc._openai_service, ...) targets the same instance the router uses.
    """
    app.dependency_overrides[get_llm_service] = lambda: _openai_service
    return TestClient(app)
