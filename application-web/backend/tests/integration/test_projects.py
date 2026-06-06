from __future__ import annotations

import uuid


class TestListProjects:
    async def test_returns_empty_list_for_new_user(self, client, auth_headers):
        resp = await client.get("/v1/projects", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_requires_authentication(self, client):
        resp = await client.get("/v1/projects")
        assert resp.status_code == 401


class TestCreateProject:
    async def test_creates_project_returns_201(self, client, auth_headers):
        resp = await client.post(
            "/v1/projects",
            json={"name": "Admin Portal", "description": "B2B SaaS admin", "project_type": "web_saas"},
            headers=auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["name"] == "Admin Portal"
        assert body["project_type"] == "web_saas"
        assert "id" in body
        assert "created_at" in body

    async def test_created_project_appears_in_list(self, client, auth_headers):
        project_name = f"Visible_{uuid.uuid4().hex[:6]}"
        await client.post(
            "/v1/projects",
            json={"name": project_name},
            headers=auth_headers,
        )
        resp = await client.get("/v1/projects", headers=auth_headers)
        assert resp.status_code == 200
        names = [p["name"] for p in resp.json()]
        assert project_name in names

    async def test_empty_name_returns_422(self, client, auth_headers):
        resp = await client.post(
            "/v1/projects",
            json={"name": ""},
            headers=auth_headers,
        )
        assert resp.status_code == 422

    async def test_requires_authentication(self, client):
        resp = await client.post("/v1/projects", json={"name": "No Auth"})
        assert resp.status_code == 401


class TestGetProject:
    async def test_returns_project_by_id(self, client, auth_headers):
        create = await client.post(
            "/v1/projects", json={"name": "Detail Project"}, headers=auth_headers
        )
        project_id = create.json()["id"]
        resp = await client.get(f"/v1/projects/{project_id}", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == project_id
        assert resp.json()["name"] == "Detail Project"

    async def test_returns_404_for_unknown_id(self, client, auth_headers):
        resp = await client.get(f"/v1/projects/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_returns_404_for_another_users_project(self, client, auth_headers):
        create = await client.post(
            "/v1/projects", json={"name": "User A Project"}, headers=auth_headers
        )
        project_id = create.json()["id"]

        email_b = f"userb_{uuid.uuid4().hex[:8]}@example.com"
        reg_b = await client.post(
            "/v1/auth/register", json={"email": email_b, "password": "PassB1234!"}
        )
        headers_b = {"Authorization": f"Bearer {reg_b.json()['access_token']}"}

        resp = await client.get(f"/v1/projects/{project_id}", headers=headers_b)
        assert resp.status_code == 404


class TestUpdateProject:
    async def test_patch_updates_name_and_description(self, client, auth_headers):
        create = await client.post(
            "/v1/projects", json={"name": "Old Name"}, headers=auth_headers
        )
        project_id = create.json()["id"]
        resp = await client.patch(
            f"/v1/projects/{project_id}",
            json={"name": "New Name", "description": "Updated desc"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "New Name"
        assert body["description"] == "Updated desc"

    async def test_patch_nonexistent_project_returns_404(self, client, auth_headers):
        resp = await client.patch(
            f"/v1/projects/{uuid.uuid4()}",
            json={"name": "Phantom"},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    async def test_patch_preserves_unset_fields(self, client, auth_headers):
        create = await client.post(
            "/v1/projects",
            json={"name": "Stable", "project_type": "web_saas"},
            headers=auth_headers,
        )
        project_id = create.json()["id"]
        await client.patch(
            f"/v1/projects/{project_id}",
            json={"description": "new desc"},
            headers=auth_headers,
        )
        resp = await client.get(f"/v1/projects/{project_id}", headers=auth_headers)
        assert resp.json()["name"] == "Stable"
        assert resp.json()["project_type"] == "web_saas"


class TestDeleteProject:
    async def test_delete_returns_204(self, client, auth_headers):
        create = await client.post(
            "/v1/projects", json={"name": "To Delete"}, headers=auth_headers
        )
        project_id = create.json()["id"]
        resp = await client.delete(f"/v1/projects/{project_id}", headers=auth_headers)
        assert resp.status_code == 204

    async def test_deleted_project_returns_404_on_get(self, client, auth_headers):
        create = await client.post(
            "/v1/projects", json={"name": "Temp Project"}, headers=auth_headers
        )
        project_id = create.json()["id"]
        await client.delete(f"/v1/projects/{project_id}", headers=auth_headers)
        resp = await client.get(f"/v1/projects/{project_id}", headers=auth_headers)
        assert resp.status_code == 404

    async def test_delete_nonexistent_returns_404(self, client, auth_headers):
        resp = await client.delete(f"/v1/projects/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404
