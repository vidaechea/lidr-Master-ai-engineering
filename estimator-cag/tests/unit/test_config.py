"""Unit tests for app.config.Settings — router failover policy defaults."""
import pytest

from app.config import Settings


class TestRouterPolicyDefaults:
    """Settings must ship sensible defaults so the Router works out of the box."""

    def test_router_num_retries_default(self):
        s = Settings()
        assert s.router_num_retries == 2

    def test_router_timeout_default(self):
        s = Settings()
        assert s.router_timeout == 30.0

    def test_router_retry_after_default(self):
        s = Settings()
        assert s.router_retry_after == 5

    def test_router_allowed_fails_default(self):
        s = Settings()
        assert s.router_allowed_fails == 2

    def test_router_cooldown_time_default(self):
        s = Settings()
        assert s.router_cooldown_time == 60

    def test_router_num_retries_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("ROUTER_NUM_RETRIES", "5")
        s = Settings()
        assert s.router_num_retries == 5

    def test_router_timeout_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("ROUTER_TIMEOUT", "60.0")
        s = Settings()
        assert s.router_timeout == 60.0

    def test_router_retry_after_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("ROUTER_RETRY_AFTER", "10")
        s = Settings()
        assert s.router_retry_after == 10

    def test_router_allowed_fails_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("ROUTER_ALLOWED_FAILS", "3")
        s = Settings()
        assert s.router_allowed_fails == 3

    def test_router_cooldown_time_overridable_via_env(self, monkeypatch):
        monkeypatch.setenv("ROUTER_COOLDOWN_TIME", "120")
        s = Settings()
        assert s.router_cooldown_time == 120

    def test_router_num_retries_is_int(self):
        s = Settings()
        assert isinstance(s.router_num_retries, int)

    def test_router_timeout_is_float(self):
        s = Settings()
        assert isinstance(s.router_timeout, float)

    def test_router_retry_after_is_int(self):
        s = Settings()
        assert isinstance(s.router_retry_after, int)

    def test_router_allowed_fails_is_int(self):
        s = Settings()
        assert isinstance(s.router_allowed_fails, int)

    def test_router_cooldown_time_is_int(self):
        s = Settings()
        assert isinstance(s.router_cooldown_time, int)
