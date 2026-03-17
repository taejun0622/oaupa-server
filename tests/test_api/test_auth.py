import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        email = f"reg-{uuid.uuid4().hex[:8]}@test.com"
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "securepass123", "full_name": "New User"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == email
        assert data["full_name"] == "New User"
        assert "id" in data
        assert "password_hash" not in data

    async def test_register_duplicate_email(self, client: AsyncClient):
        email = f"dup-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "pass123"},
        )
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "pass456"},
        )
        assert resp.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "pass123"},
        )
        assert resp.status_code == 422

    async def test_register_missing_password(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/register",
            json={"email": "test@test.com"},
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        email = f"login-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correct123"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "correct123"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        email = f"wrongpw-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "correct123"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@test.com", "password": "pass"},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient):
        email = f"refresh-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "pass123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "pass123"},
        )
        refresh_token = login_resp.json()["refresh_token"]
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_invalid_token(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert resp.status_code == 401

    async def test_refresh_with_access_token_rejected(self, client: AsyncClient):
        email = f"refacc-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "pass123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "pass123"},
        )
        access_token = login_resp.json()["access_token"]
        resp = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": access_token},
        )
        assert resp.status_code == 401
