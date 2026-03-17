import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestUsers:
    async def test_get_me(self, client: AsyncClient):
        headers = await auth_headers(client)
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "id" in data
        assert "email" in data
        assert "password_hash" not in data

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code in (401, 422)

    async def test_update_me(self, client: AsyncClient):
        headers = await auth_headers(client)
        resp = await client.patch(
            "/api/v1/users/me",
            json={"full_name": "Updated Name"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["full_name"] == "Updated Name"

    async def test_change_password(self, client: AsyncClient):
        import uuid
        email = f"chpw-{uuid.uuid4().hex[:8]}@test.com"
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "oldpass123"},
        )
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "oldpass123"},
        )
        headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        resp = await client.put(
            "/api/v1/users/me/password",
            json={"current_password": "oldpass123", "new_password": "newpass456"},
            headers=headers,
        )
        assert resp.status_code == 204

        # Login with new password works
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "newpass456"},
        )
        assert resp.status_code == 200

    async def test_change_password_wrong_current(self, client: AsyncClient):
        headers = await auth_headers(client)
        resp = await client.put(
            "/api/v1/users/me/password",
            json={"current_password": "wrong", "new_password": "new123"},
            headers=headers,
        )
        assert resp.status_code == 400
