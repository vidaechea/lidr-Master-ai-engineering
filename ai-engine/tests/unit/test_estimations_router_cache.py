from app.routers.estimations import get_cached_estimation_service
from app.services.cache_service import CachedEstimationService
from app.services.estimation_service import EstimationService


def test_get_cached_estimation_service_returns_base_service_when_cache_disabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_enabled", False)
    service = get_cached_estimation_service()

    assert isinstance(service, EstimationService)
    assert not isinstance(service, CachedEstimationService)


def test_get_cached_estimation_service_returns_cached_service_when_cache_enabled(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "cache_enabled", True)
    service = get_cached_estimation_service()

    assert isinstance(service, CachedEstimationService)
