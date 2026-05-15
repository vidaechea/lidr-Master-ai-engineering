import logging

import pytest
from fastapi.testclient import TestClient

# Prevent asyncio's 'Using proactor' debug message from writing to a closed
# stdout stream when litellm's atexit cleanup handler runs after pytest exits.
logging.getLogger("asyncio").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Synchronous test client for integration tests."""
    from app.main import app  # lazy import: avoids loading litellm in unit tests
    return TestClient(app)


@pytest.fixture(autouse=True)
def disable_cache(monkeypatch):
    """Disable cache for all tests."""
    from app.config import settings
    monkeypatch.setattr(settings, "cache_enabled", False)
