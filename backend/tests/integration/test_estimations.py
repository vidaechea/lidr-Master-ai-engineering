from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

# Minimum valid transcription (>= 20 chars per EstimationCreate schema)
VALID_TRANSCRIPTION = (
    "A B2B SaaS company needs an admin portal to manage customer accounts "
    "with SSO, user management, and full audit logging."
)

AI_RESPONSE_PAYLOAD = {
    "estimation": "## Admin Portal\n1. Auth & SSO: 40h\n**Total: 40h**",
    "model": "gpt-4o-mini",
    "input_tokens": 450,
    "output_tokens": 180,
    "turn_cost_usd": 0.00060,
    "total_cost_usd": 0.00060,
    "requirements": "- SSO\n- User list\n- Audit log",
    "validation": {"warnings": []},
    "structured_result": {"phases": [{"name": "Auth & SSO", "hours": 40}]},
    "prompt_version": "v1",
}


def _patch_ai_sync(payload=None):
    return patch(
        "app.services.ai_client.estimate_sync",
        AsyncMock(return_value=payload or AI_RESPONSE_PAYLOAD),
    )


def _patch_ai_enqueue(job_id="job-test-001"):
    return patch(
        "app.services.ai_client.enqueue_async",
        AsyncMock(return_value=job_id),
    )


class TestListEstimations:
    async def test_returns_empty_list_for_new_user(self, client, auth_headers):
        resp = await client.get("/v1/estimations", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_requires_authentication(self, client):
        resp = await client.get("/v1/estimations")
        assert resp.status_code == 401


class TestCreateEstimationSync:
    async def test_returns_201_with_completed_status(self, client, auth_headers):
        with _patch_ai_sync():
            resp = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "completed"
        assert body["estimation_markdown"] == AI_RESPONSE_PAYLOAD["estimation"]
        assert body["model_used"] == "gpt-4o-mini"
        assert body["input_tokens"] == 450
        assert body["output_tokens"] == 180

    async def test_associates_with_project_when_provided(self, client, auth_headers):
        proj = await client.post(
            "/v1/projects", json={"name": "SaaS Portal"}, headers=auth_headers
        )
        project_id = proj.json()["id"]
        with _patch_ai_sync():
            resp = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION, "project_id": project_id},
                headers=auth_headers,
            )
        assert resp.status_code == 201
        assert resp.json()["project_id"] == project_id

    async def test_short_transcription_returns_422(self, client, auth_headers):
        resp = await client.post(
            "/v1/estimations",
            json={"transcription": "too short"},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_ai_engine_502_propagates_to_caller(self, client, auth_headers):
        from fastapi import HTTPException

        with patch(
            "app.services.ai_client.estimate_sync",
            AsyncMock(side_effect=HTTPException(status_code=502, detail="AI Engine returned 502")),
        ):
            resp = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        assert resp.status_code == 502

    async def test_requires_authentication(self, client):
        resp = await client.post(
            "/v1/estimations", json={"transcription": VALID_TRANSCRIPTION}
        )
        assert resp.status_code == 401

    async def test_estimation_appears_in_list_after_creation(self, client, auth_headers):
        with _patch_ai_sync():
            create = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        estimation_id = create.json()["id"]
        resp = await client.get("/v1/estimations", headers=auth_headers)
        ids = [e["id"] for e in resp.json()]
        assert estimation_id in ids


class TestGetEstimation:
    async def test_returns_estimation_by_id(self, client, auth_headers):
        with _patch_ai_sync():
            create = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        estimation_id = create.json()["id"]
        resp = await client.get(f"/v1/estimations/{estimation_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == estimation_id

    async def test_returns_404_for_unknown_id(self, client, auth_headers):
        resp = await client.get(f"/v1/estimations/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_returns_404_for_another_users_estimation(self, client, auth_headers):
        with _patch_ai_sync():
            create = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        estimation_id = create.json()["id"]

        email_b = f"other_{uuid.uuid4().hex[:8]}@example.com"
        reg_b = await client.post(
            "/v1/auth/register", json={"email": email_b, "password": "OtherPass99!"}
        )
        headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}
        resp = await client.get(f"/v1/estimations/{estimation_id}", headers=headers_b)
        assert resp.status_code == 404


class TestGetEstimationStatus:
    async def test_returns_status_and_completed_at_fields(self, client, auth_headers):
        with _patch_ai_sync():
            create = await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        estimation_id = create.json()["id"]
        resp = await client.get(
            f"/v1/estimations/{estimation_id}/status", headers=auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert "completed_at" in body
        assert body["id"] == estimation_id

    async def test_returns_404_for_unknown_id(self, client, auth_headers):
        resp = await client.get(
            f"/v1/estimations/{uuid.uuid4()}/status", headers=auth_headers
        )
        assert resp.status_code == 404


class TestListEstimationsFilter:
    async def test_filter_by_status_returns_only_matching(self, client, auth_headers):
        with _patch_ai_sync():
            await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        resp = await client.get(
            "/v1/estimations?status_filter=completed", headers=auth_headers
        )
        assert resp.status_code == 200
        assert all(e["status"] == "completed" for e in resp.json())

    async def test_filter_by_nonexistent_status_returns_empty(self, client, auth_headers):
        with _patch_ai_sync():
            await client.post(
                "/v1/estimations",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        resp = await client.get(
            "/v1/estimations?status_filter=pending", headers=auth_headers
        )
        assert resp.status_code == 200
        assert resp.json() == []


class TestAsyncEstimation:
    async def test_async_endpoint_returns_202_with_pending_status(self, client, auth_headers):
        with _patch_ai_enqueue("job-async-001"):
            resp = await client.post(
                "/v1/estimations/async",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        assert resp.status_code == 202
        body = resp.json()
        assert body["status"] == "pending"
        assert "estimation_id" in body
        assert body["job_id"] == "job-async-001"

    async def test_async_requires_authentication(self, client):
        resp = await client.post(
            "/v1/estimations/async", json={"transcription": VALID_TRANSCRIPTION}
        )
        assert resp.status_code == 401


class TestEstimationCallback:
    async def test_callback_with_unknown_job_returns_404(self, client):
        resp = await client.post(
            "/v1/internal/estimation-callback",
            json={
                "job_id": f"nonexistent-{uuid.uuid4().hex}",
                "status": "failed",
                "result": None,
                "error": "LLM timeout",
            },
        )
        assert resp.status_code == 404

    async def test_callback_applies_completed_result(self, client, auth_headers):
        job_id = f"job-cb-{uuid.uuid4().hex[:8]}"
        with _patch_ai_enqueue(job_id):
            create = await client.post(
                "/v1/estimations/async",
                json={"transcription": VALID_TRANSCRIPTION},
                headers=auth_headers,
            )
        estimation_id = create.json()["estimation_id"]

        # Patch the JSONB job lookup (PostgreSQL-specific) to return the pending estimation
        with patch(
            "app.routers.internal.estimation_service.get_estimation_by_job",
            AsyncMock(return_value=None),
        ):
            pass  # probe that it's patchable; real test below uses inline mock

        # Use mock to bypass the JSONB path query (not supported in SQLite)
        from app.services import estimation_service as est_svc

        async def _fake_get_by_job(db, jid):
            if jid == job_id:
                result = await est_svc.get_estimation(
                    db, uuid.UUID(estimation_id), None  # type: ignore[arg-type]
                )
                # get_estimation filters by user_id; bypass with raw query
                from sqlalchemy import select
                from app.models.estimation import Estimation
                row = await db.execute(
                    select(Estimation).where(Estimation.id == uuid.UUID(estimation_id))
                )
                return row.scalar_one_or_none()
            return None

        with patch(
            "app.routers.internal.estimation_service.get_estimation_by_job",
            side_effect=_fake_get_by_job,
        ):
            resp = await client.post(
                "/v1/internal/estimation-callback",
                json={
                    "job_id": job_id,
                    "status": "completed",
                    "result": AI_RESPONSE_PAYLOAD,
                    "error": None,
                },
            )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        get_resp = await client.get(
            f"/v1/estimations/{estimation_id}", headers=auth_headers
        )
        assert get_resp.json()["status"] == "completed"
        assert get_resp.json()["estimation_markdown"] == AI_RESPONSE_PAYLOAD["estimation"]
