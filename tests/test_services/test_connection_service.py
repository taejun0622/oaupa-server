import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.token_vault import TokenVault
from app.services import connection_service


@pytest.mark.asyncio
class TestListConnections:
    async def test_returns_project_connections(
        self, db: AsyncSession, test_project: Project, test_connection: OAuthConnection
    ):
        connections = await connection_service.list_connections(db, test_project.id)
        assert len(connections) >= 1
        assert any(c.id == test_connection.id for c in connections)

    async def test_empty_for_other_project(self, db: AsyncSession):
        connections = await connection_service.list_connections(db, uuid.uuid4())
        assert connections == []


@pytest.mark.asyncio
class TestGetConnection:
    async def test_success(
        self, db: AsyncSession, test_project: Project, test_connection: OAuthConnection
    ):
        conn = await connection_service.get_connection(db, test_project.id, test_connection.id)
        assert conn.id == test_connection.id

    async def test_not_found(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await connection_service.get_connection(db, test_project.id, uuid.uuid4())

    async def test_wrong_project(self, db: AsyncSession, test_connection: OAuthConnection):
        with pytest.raises(NotFoundError):
            await connection_service.get_connection(db, uuid.uuid4(), test_connection.id)


@pytest.mark.asyncio
class TestRevokeConnection:
    async def test_revoke_sets_status(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        with patch(
            "app.services.connection_service.get_provider_instance",
            new_callable=AsyncMock,
        ) as mock_gpi:
            mock_provider = AsyncMock()
            mock_provider.revoke_token = AsyncMock(return_value=True)
            mock_gpi.return_value = (None, mock_provider)

            await connection_service.revoke_connection(
                db, test_project.id, test_connection.id
            )

        assert test_connection.status == "revoked"

    async def test_revoke_not_found(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await connection_service.revoke_connection(db, test_project.id, uuid.uuid4())

    async def test_revoke_continues_on_provider_error(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        with patch(
            "app.services.connection_service.get_provider_instance",
            new_callable=AsyncMock,
            side_effect=Exception("Provider error"),
        ):
            await connection_service.revoke_connection(
                db, test_project.id, test_connection.id
            )
        # Should still be revoked even if provider call fails
        assert test_connection.status == "revoked"
