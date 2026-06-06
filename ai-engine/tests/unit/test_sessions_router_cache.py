from app.api.sessions import _get_cached_estimation_service
from app.generation.cag.cache_service import CachedEstimationService
from app.domain.estimation_service import EstimationService


def test_get_cached_estimation_service_returns_base_service_when_cache_disabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_enabled", False)
    service = _get_cached_estimation_service()

    assert isinstance(service, EstimationService)
    assert not isinstance(service, CachedEstimationService)


def test_get_cached_estimation_service_returns_cached_service_when_cache_enabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_enabled", True)
    service = _get_cached_estimation_service()

    assert isinstance(service, CachedEstimationService)

