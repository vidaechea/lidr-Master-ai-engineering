from __future__ import annotations

import pytest

from app.services import ai_client


class TestRuntimeModelConfigClient:
    async def test_get_runtime_models_calls_request_helper(self, monkeypatch: pytest.MonkeyPatch):
        captured: dict[str, object] = {}

        async def _fake_request(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return {"models": {}, "available_models": ["gpt-4o-mini"]}

        monkeypatch.setattr(ai_client, "_request_ai_engine", _fake_request)

        payload = await ai_client.get_runtime_models()

        assert payload["available_models"] == ["gpt-4o-mini"]
        assert captured["args"] == ("GET", "/api/v1/config/models")

    async def test_update_runtime_models_calls_request_helper(self, monkeypatch: pytest.MonkeyPatch):
        captured: dict[str, object] = {}

        async def _fake_request(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return {"models": {}, "available_models": ["gpt-4o-mini"]}

        monkeypatch.setattr(ai_client, "_request_ai_engine", _fake_request)

        payload = await ai_client.update_runtime_models({"LLM_MODEL": "gpt-5.4-mini"})

        assert payload["available_models"] == ["gpt-4o-mini"]
        assert captured["args"] == ("PUT", "/api/v1/config/models")
        assert captured["kwargs"]["json_body"] == {"models": {"LLM_MODEL": "gpt-5.4-mini"}}
