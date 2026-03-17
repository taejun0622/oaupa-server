import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.models.api_key import ApiKey
from app.models.user import User


@pytest.mark.asyncio
class TestGetCurrentUser:
    async def test_valid_bearer(self, client: AsyncClient, test_user: User):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_user.id)

    async def test_missing_authorization_header(self, client: AsyncClient):
        resp = await client.get("/api/v1/users/me")
        assert resp.status_code in (401, 422)

    async def test_invalid_bearer_prefix(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Basic abc123"},
        )
        assert resp.status_code == 401

    async def test_expired_token(self, client: AsyncClient, test_user: User):
        token = create_access_token(str(test_user.id), expires_delta=timedelta(seconds=-1))
        resp = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_inactive_user(self, client: AsyncClient, db: AsyncSession):
        from app.core.security import hash_password

        user = User(
            email=f"inactive-{uuid.uuid4().hex[:8]}@test.com",
            password_hash=hash_password("pass"),
            is_active=False,
        )
        db.add(user)
        await db.flush()
        headers = {"Authorization": f"Bearer {create_access_token(str(user.id))}"}
        resp = await client.get("/api/v1/users/me", headers=headers)
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestResolveApiKey:
    async def test_valid_api_key(
        self, client: AsyncClient, test_api_key: tuple[ApiKey, str], test_project
    ):
        from app.models.oauth_connection import OAuthConnection
        _api_key, full_key = test_api_key
        # Use tokens endpoint which requires API key
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            params={"provider": "nonexistent"},
            headers={"X-API-Key": full_key},
        )
        # 404 = auth succeeded, just no connection found
        assert resp.status_code == 404

    async def test_invalid_api_key(self, client: AsyncClient, test_project):
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            params={"provider": "test"},
            headers={"X-API-Key": "oau_live_bogus"},
        )
        assert resp.status_code == 401

    async def test_expired_api_key(self, client: AsyncClient, db: AsyncSession, test_project):
        full_key = f"oau_live_expired{uuid.uuid4().hex}"
        api_key = ApiKey(
            project_id=test_project.id,
            name="Expired",
            key_prefix=full_key[:12],
            key_hash=hashlib.sha256(full_key.encode()).hexdigest(),
            scopes=["tokens:read"],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        db.add(api_key)
        await db.flush()

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            params={"provider": "test"},
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestGetCurrentSuperadmin:
    async def test_superadmin_passes(self, client: AsyncClient, test_superadmin: User):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_superadmin.id))}"}
        resp = await client.get("/api/v1/admin/stats", headers=headers)
        assert resp.status_code == 200

    async def test_non_superadmin_rejected(self, client: AsyncClient, test_user: User):
        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.get("/api/v1/admin/stats", headers=headers)
        assert resp.status_code == 403
