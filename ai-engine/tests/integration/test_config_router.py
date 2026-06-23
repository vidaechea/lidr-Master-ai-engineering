from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.api import config as config_api
from app.dependencies import get_runtime_config
from app.main import app


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
        await asyncio.sleep(0)
        model = self._overrides.get("LLM_MODEL", "gpt-4o-mini")
        fallback = self._overrides.get("LLM_FALLBACK", "claude-haiku-4-5-20251001")
        critic = self._overrides.get("CRITIC_MODEL", "gpt-4o-mini")
        metadata_extractor = self._overrides.get("METADATA_EXTRACTOR_MODEL", "gpt-4o-mini")
        compression = self._overrides.get("COMPRESSION_MODEL", "gpt-4o-mini")
        propositional = self._overrides.get("PROPOSITIONAL_CHUNKER_MODEL", "gpt-4o-mini")
        contextual = self._overrides.get("CONTEXTUAL_CHUNKER_MODEL", "gpt-4o-mini")
        return {
            "LLM_MODEL": _Entry(model, "gpt-4o-mini", "LLM_MODEL" in self._overrides),
            "LLM_FALLBACK": _Entry(
                fallback,
                "claude-haiku-4-5-20251001",
                "LLM_FALLBACK" in self._overrides,
            ),
            "CRITIC_MODEL": _Entry(critic, "gpt-4o-mini", "CRITIC_MODEL" in self._overrides),
            "METADATA_EXTRACTOR_MODEL": _Entry(
                metadata_extractor,
                "gpt-4o-mini",
                "METADATA_EXTRACTOR_MODEL" in self._overrides,
            ),
            "COMPRESSION_MODEL": _Entry(
                compression,
                "gpt-4o-mini",
                "COMPRESSION_MODEL" in self._overrides,
            ),
            "PROPOSITIONAL_CHUNKER_MODEL": _Entry(
                propositional,
                "gpt-4o-mini",
                "PROPOSITIONAL_CHUNKER_MODEL" in self._overrides,
            ),
            "CONTEXTUAL_CHUNKER_MODEL": _Entry(
                contextual,
                "gpt-4o-mini",
                "CONTEXTUAL_CHUNKER_MODEL" in self._overrides,
            ),
        }

    async def set_overrides(self, changes: dict[str, str | None]) -> None:
        await asyncio.sleep(0)
        for key, value in changes.items():
            if value is None:
                self._overrides.pop(key, None)
            else:
                self._overrides[key] = value


def test_get_runtime_models(client, monkeypatch):
    stub = _StubRuntimeConfig()
    app.dependency_overrides[get_runtime_config] = lambda: stub

    try:
        response = client.get("/api/v1/config/models")
    finally:
        app.dependency_overrides.pop(get_runtime_config, None)

    assert response.status_code == 200
    body = response.json()
    assert "models" in body
    assert "available_models" in body
    assert body["models"]["LLM_MODEL"]["effective"] == "gpt-4o-mini"


def test_update_runtime_models(client, monkeypatch):
    stub = _StubRuntimeConfig()
    app.dependency_overrides[get_runtime_config] = lambda: stub

    refreshed: dict[str, str] = {}

    def _fake_refresh(primary_model: str | None = None, fallback_model: str | None = None):
        refreshed["primary"] = primary_model or ""
        refreshed["fallback"] = fallback_model or ""
        return object()

    monkeypatch.setattr(config_api, "create_litellm_router_service", _fake_refresh)

    try:
        response = client.put(
            "/api/v1/config/models",
            json={"models": {"LLM_MODEL": "gpt-5.4-mini"}},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_config, None)

    assert response.status_code == 200
    body = response.json()
    assert body["models"]["LLM_MODEL"]["effective"] == "gpt-5.4-mini"
    assert refreshed["primary"] == "gpt-5.4-mini"
    assert refreshed["fallback"] == "claude-haiku-4-5-20251001"


def test_update_runtime_models_rejects_invalid_key(client, monkeypatch):
    stub = _StubRuntimeConfig()
    app.dependency_overrides[get_runtime_config] = lambda: stub

    try:
        response = client.put(
            "/api/v1/config/models",
            json={"models": {"BAD_KEY": "gpt-4o-mini"}},
        )
    finally:
        app.dependency_overrides.pop(get_runtime_config, None)

    assert response.status_code == 422


def test_get_runtime_status(client):
    stub = _StubRuntimeConfig()
    app.dependency_overrides[get_runtime_config] = lambda: stub

    try:
        response = client.get("/api/v1/config/runtime-status")
    finally:
        app.dependency_overrides.pop(get_runtime_config, None)

    assert response.status_code == 200
    body = response.json()
    assert "llm_routing" in body
    assert body["conversation"]["metadata_extractor"]["mode"] == "heuristic_only"
    assert body["conversation"]["compression"]["mode"] == "summarizer_heuristic"
