from __future__ import annotations

from unittest.mock import AsyncMock

import pytest


@pytest.mark.asyncio
async def test_profile_crud_and_default_resolution(client, auth_headers, monkeypatch):
    monkeypatch.setattr(
        "app.services.ai_client.rag_agent_structure",
        AsyncMock(return_value={"estimate": {"summary": "ok", "low_confidence": False, "modules": [], "line_items": [], "assumptions": [], "sources": []}, "agent_trace": {"steps": []}}),
    )

    create_response = await client.post(
        "/v1/rag/agent/profiles",
        headers=auth_headers,
        json={
            "name": "Default",
            "persona": "Be conservative",
            "is_default": True,
            "config": {
                "model": "gpt-5-mini",
                "reasoning_effort": "low",
                "max_iterations": 4,
                "search_top_k": 7,
                "search_distance_threshold": 0.42,
            },
        },
    )
    assert create_response.status_code == 201
    profile_id = create_response.json()["id"]

    list_response = await client.get("/v1/rag/agent/profiles", headers=auth_headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1

    structure_response = await client.post(
        "/v1/rag/agent/structure",
        headers=auth_headers,
        json={
            "query": {
                "search_text": "Backend and mobile",
                "chunk_types": ["budget_component"],
                "keywords": ["backend"],
            },
            "profile_id": profile_id,
        },
    )
    assert structure_response.status_code == 200
    assert "estimate" in structure_response.json()


@pytest.mark.asyncio
async def test_agent_hours_uses_default_profile_overrides(client, auth_headers, monkeypatch):
    captured = {}

    async def _fake_agent_hours(payload):
        captured.update(payload)
        return {"tasks": [], "agent_trace": {"steps": []}}

    monkeypatch.setattr("app.services.ai_client.rag_agent_hours", _fake_agent_hours)

    create_response = await client.post(
        "/v1/rag/agent/profiles",
        headers=auth_headers,
        json={
            "name": "Veloz",
            "is_default": True,
            "config": {
                "model": "gpt-5-mini",
                "reasoning_effort": "low",
                "max_iterations": 3,
                "search_top_k": 6,
            },
        },
    )
    assert create_response.status_code == 201

    hours_response = await client.post(
        "/v1/rag/agent/hours",
        headers=auth_headers,
        json={
            "modules": [
                {
                    "name": "Auth",
                    "tasks": [{"name": "OAuth backend"}],
                }
            ]
        },
    )
    assert hours_response.status_code == 200
    assert captured["model"] == "gpt-5-mini"
    assert captured["reasoning_effort"] == "low"
    assert captured["max_iterations"] == 3
    assert captured["search_top_k"] == 6
