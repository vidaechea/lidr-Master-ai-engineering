from __future__ import annotations

import uuid


class TestRegister:
    async def test_register_returns_201_with_tokens(self, client):
        email = f"reg_{uuid.uuid4().hex[:8]}@example.com"
        resp = await client.post(
            "/v1/auth/register",
            json={"email": email, "password": "Password123!", "full_name": "Alice"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_register_duplicate_email_returns_400(self, client):
        email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
        payload = {"email": email, "password": "Password123!"}
        await client.post("/v1/auth/register", json=payload)
        resp = await client.post("/v1/auth/register", json=payload)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    async def test_register_short_password_returns_422(self, client):
        resp = await client.post(
            "/v1/auth/register",
            json={"email": "short@example.com", "password": "abc"},
        )
        assert resp.status_code == 422

    async def test_register_invalid_email_returns_422(self, client):
        resp = await client.post(
            "/v1/auth/register",
            json={"email": "not-an-email", "password": "Password123!"},
        )
        assert resp.status_code == 422


class TestLogin:
    async def test_login_returns_tokens(self, client):
        email = f"login_{uuid.uuid4().hex[:8]}@example.com"
        password = "LoginPass99!"
        await client.post("/v1/auth/register", json={"email": email, "password": password})
        resp = await client.post(
            "/v1/auth/login",
            data={"username": email, "password": password},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_login_wrong_password_returns_401(self, client):
        email = f"wrong_{uuid.uuid4().hex[:8]}@example.com"
        await client.post("/v1/auth/register", json={"email": email, "password": "Correct123!"})
        resp = await client.post(
            "/v1/auth/login",
            data={"username": email, "password": "WrongPassword"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_email_returns_401(self, client):
        resp = await client.post(
            "/v1/auth/login",
            data={"username": "nouser@example.com", "password": "anything"},
        )
        assert resp.status_code == 401


class TestRefreshToken:
    async def test_refresh_returns_new_tokens(self, client, registered_user):
        resp = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": registered_user["refresh_token"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_refresh_with_access_token_returns_401(self, client, registered_user):
        resp = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": registered_user["access_token"]},
        )
        assert resp.status_code == 401
        assert "Not a refresh token" in resp.json()["detail"]

    async def test_refresh_with_garbage_token_returns_401(self, client):
        resp = await client.post(
            "/v1/auth/refresh",
            json={"refresh_token": "garbage.token.value"},
        )
        assert resp.status_code == 401
