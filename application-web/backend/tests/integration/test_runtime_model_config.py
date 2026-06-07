from __future__ import annotations

from unittest.mock import AsyncMock, patch


RUNTIME_MODELS_PAYLOAD = {
    "models": {
        "LLM_MODEL": {
            "effective": "gpt-4o-mini",
            "default": "gpt-4o-mini",
            "overridden": False,
        },
        "LLM_FALLBACK": {
            "effective": "claude-haiku-4-5-20251001",
            "default": "claude-haiku-4-5-20251001",
            "overridden": False,
        },
    },
    "available_models": ["gpt-4o-mini", "gpt-5.4-mini", "claude-haiku-4-5-20251001"],
}


class TestRuntimeModelConfigEndpoints:
    async def test_get_runtime_models_requires_auth(self, client):
        response = await client.get("/v1/estimations/config/models")
        assert response.status_code == 401

    async def test_get_runtime_models_returns_proxy_payload(self, client, auth_headers):
        with patch(
            "app.services.ai_client.get_runtime_models",
            AsyncMock(return_value=RUNTIME_MODELS_PAYLOAD),
        ):
            response = await client.get("/v1/estimations/config/models", headers=auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["models"]["LLM_MODEL"]["effective"] == "gpt-4o-mini"
        assert "gpt-5.4-mini" in body["available_models"]

    async def test_put_runtime_models_forwards_changes(self, client, auth_headers):
        expected = {
            **RUNTIME_MODELS_PAYLOAD,
            "models": {
                **RUNTIME_MODELS_PAYLOAD["models"],
                "LLM_MODEL": {
                    "effective": "gpt-5.4-mini",
                    "default": "gpt-4o-mini",
                    "overridden": True,
                },
            },
        }

        with patch(
            "app.services.ai_client.update_runtime_models",
            AsyncMock(return_value=expected),
        ) as mock_update:
            response = await client.put(
                "/v1/estimations/config/models",
                json={"models": {"LLM_MODEL": "gpt-5.4-mini"}},
                headers=auth_headers,
            )

        assert response.status_code == 200
        assert response.json()["models"]["LLM_MODEL"]["effective"] == "gpt-5.4-mini"
        mock_update.assert_awaited_once_with({"LLM_MODEL": "gpt-5.4-mini"})
