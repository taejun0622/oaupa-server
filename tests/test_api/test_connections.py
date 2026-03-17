import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.user import User
from app.models.token_vault import TokenVault
from tests.conftest import auth_headers, create_project_via_api


@pytest.mark.asyncio
class TestConnections:
    async def test_list_connections(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_user: User,
        test_project: Project,
        test_connection: OAuthConnection,
    ):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/connections",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["provider_id"] == test_connection.provider_id

    async def test_get_connection(
        self,
        client: AsyncClient,
        test_user: User,
        test_project: Project,
        test_connection: OAuthConnection,
    ):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/connections/{test_connection.id}",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(test_connection.id)

    async def test_get_connection_wrong_project(self, client: AsyncClient):
        headers = await auth_headers(client)
        fake_project = str(uuid.uuid4())
        fake_conn = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/projects/{fake_project}/connections/{fake_conn}",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_revoke_connection(
        self,
        client: AsyncClient,
        db: AsyncSession,
        test_user: User,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}

        with patch("app.services.connection_service.get_provider_instance", new_callable=AsyncMock) as mock_gpi:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock(return_value=True)
            mock_gpi.return_value = (None, mock_provider)

            resp = await client.delete(
                f"/api/v1/projects/{test_project.id}/connections/{test_connection.id}",
                headers=headers,
            )
            assert resp.status_code == 204

        await db.refresh(test_connection)
        assert test_connection.status == "revoked"
