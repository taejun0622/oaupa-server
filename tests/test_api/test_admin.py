import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.user import User
from tests.conftest import auth_headers


@pytest.mark.asyncio
class TestAdmin:
    async def test_list_users_as_superadmin(
        self, client: AsyncClient, test_superadmin: User
    ):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_superadmin.id))}"}
        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_stats_as_superadmin(
        self, client: AsyncClient, test_superadmin: User
    ):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_superadmin.id))}"}
        resp = await client.get("/api/v1/admin/stats", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "users" in data
        assert "projects" in data
        assert "connections" in data

    async def test_admin_forbidden_for_regular_user(self, client: AsyncClient):
        headers = await auth_headers(client)
        resp = await client.get("/api/v1/admin/users", headers=headers)
        assert resp.status_code == 403

    async def test_admin_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code in (401, 422)

    async def test_stats_forbidden_for_regular_user(self, client: AsyncClient):
        headers = await auth_headers(client)
        resp = await client.get("/api/v1/admin/stats", headers=headers)
        assert resp.status_code == 403
