from __future__ import annotations

from dataclasses import dataclass

from app.api import config as config_api


@dataclass(frozen=True)
class _Entry:
    effective: str
    default: str
    overridden: bool


class _StubRuntimeConfig:
    def __init__(self) -> None:
        self._overrides: dict[str, str] = {}

    def available_models(self) -> list[str]:
        return ["gpt-4o-mini", "gpt-5.4-mini", "claude-haiku-4-5-20251001"]

    async def snapshot(self):
        model = self._overrides.get("LLM_MODEL", "gpt-4o-mini")
        fallback = self._overrides.get("LLM_FALLBACK", "claude-haiku-4-5-20251001")
        return {
            "LLM_MODEL": _Entry(model, "gpt-4o-mini", "LLM_MODEL" in self._overrides),
            "LLM_FALLBACK": _Entry(
                fallback,
                "claude-haiku-4-5-20251001",
                "LLM_FALLBACK" in self._overrides,
            ),
        }

    async def set_overrides(self, changes: dict[str, str | None]) -> None:
        for key, value in changes.items():
            if value is None:
                self._overrides.pop(key, None)
            else:
                self._overrides[key] = value


def test_get_runtime_models(client, monkeypatch):
    stub = _StubRuntimeConfig()
    monkeypatch.setattr(config_api, "runtime_model_config", stub)

    response = client.get("/api/v1/config/models")

    assert response.status_code == 200
    body = response.json()
    assert "models" in body
    assert "available_models" in body
    assert body["models"]["LLM_MODEL"]["effective"] == "gpt-4o-mini"


def test_update_runtime_models(client, monkeypatch):
    stub = _StubRuntimeConfig()
    monkeypatch.setattr(config_api, "runtime_model_config", stub)

    refreshed: dict[str, str] = {}

    def _fake_refresh(primary_model: str | None = None, fallback_model: str | None = None):
        refreshed["primary"] = primary_model or ""
        refreshed["fallback"] = fallback_model or ""
        return object()

    monkeypatch.setattr(config_api, "create_litellm_router_service", _fake_refresh)

    response = client.put(
        "/api/v1/config/models",
        json={"models": {"LLM_MODEL": "gpt-5.4-mini"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["models"]["LLM_MODEL"]["effective"] == "gpt-5.4-mini"
    assert refreshed["primary"] == "gpt-5.4-mini"
    assert refreshed["fallback"] == "claude-haiku-4-5-20251001"


def test_update_runtime_models_rejects_invalid_key(client, monkeypatch):
    stub = _StubRuntimeConfig()
    monkeypatch.setattr(config_api, "runtime_model_config", stub)

    response = client.put(
        "/api/v1/config/models",
        json={"models": {"BAD_KEY": "gpt-4o-mini"}},
    )

    assert response.status_code == 422
