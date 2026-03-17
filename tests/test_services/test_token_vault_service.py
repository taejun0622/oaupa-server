import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt, get_current_key_version
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.token_vault import TokenVault
from app.providers.base import TokenResponse
from app.services import token_vault_service


@pytest.mark.asyncio
class TestGetToken:
    async def test_returns_decrypted_token(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        result = await token_vault_service.get_token(
            db, test_project.id, test_connection.id
        )
        assert result.access_token == "test-access-token-12345"
        assert result.token_type == "Bearer"
        assert result.connection_id == test_connection.id

    async def test_connection_not_found(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await token_vault_service.get_token(db, test_project.id, uuid.uuid4())

    async def test_revoked_connection(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        test_connection.status = "revoked"
        await db.flush()
        with pytest.raises(BadRequestError, match="revoked"):
            await token_vault_service.get_token(db, test_project.id, test_connection.id)

    async def test_auto_refresh_when_expired(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        # Set token as expired
        test_token_vault.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        await db.flush()

        mock_token_resp = TokenResponse(
            access_token="refreshed-token-999",
            refresh_token="new-refresh-token",
            expires_in=3600,
        )

        with patch(
            "app.services.token_vault_service.get_provider_instance",
            new_callable=AsyncMock,
        ) as mock_gpi:
            mock_provider = AsyncMock()
            mock_provider.refresh_token = AsyncMock(return_value=mock_token_resp)
            mock_gpi.return_value = (AsyncMock(), mock_provider)

            result = await token_vault_service.get_token(
                db, test_project.id, test_connection.id
            )

        assert result.access_token == "refreshed-token-999"


@pytest.mark.asyncio
class TestGetTokenByProvider:
    async def test_finds_connection(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        result = await token_vault_service.get_token_by_provider(
            db, test_project.id, test_connection.provider_id
        )
        assert result.access_token == "test-access-token-12345"

    async def test_no_connection(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await token_vault_service.get_token_by_provider(
                db, test_project.id, "nonexistent-provider"
            )


@pytest.mark.asyncio
class TestForceRefresh:
    async def test_refreshes_token(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
    ):
        mock_token_resp = TokenResponse(
            access_token="force-refreshed-token",
            refresh_token="new-refresh",
            expires_in=7200,
        )

        with patch(
            "app.services.token_vault_service.get_provider_instance",
            new_callable=AsyncMock,
        ) as mock_gpi:
            mock_provider = AsyncMock()
            mock_provider.refresh_token = AsyncMock(return_value=mock_token_resp)
            mock_gpi.return_value = (AsyncMock(), mock_provider)

            result = await token_vault_service.force_refresh(
                db, test_project.id, test_connection.id
            )

        assert result.access_token == "force-refreshed-token"

    async def test_not_found(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await token_vault_service.force_refresh(db, test_project.id, uuid.uuid4())


@pytest.mark.asyncio
class TestRefreshTokenInline:
    async def test_no_refresh_token_sets_expired(
        self,
        db: AsyncSession,
        test_project: Project,
        test_connection: OAuthConnection,
    ):
        # Create vault without refresh token
        vault = TokenVault(
            connection_id=test_connection.id,
            access_token_encrypted=encrypt("expired-token"),
            refresh_token_encrypted=None,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            encryption_key_id=get_current_key_version(),
        )
        db.add(vault)
        await db.flush()

        with pytest.raises(BadRequestError, match="cannot be refreshed"):
            await token_vault_service.get_token(db, test_project.id, test_connection.id)

        await db.refresh(test_connection)
        assert test_connection.status == "expired"
