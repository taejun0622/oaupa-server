import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_key import ApiKey
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.token_vault import TokenVault
from app.models.user import User


@pytest.mark.asyncio
class TestTokens:
    async def test_get_token_by_connection(
        self,
        client: AsyncClient,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
        test_api_key: tuple[ApiKey, str],
    ):
        _api_key, full_key = test_api_key
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens/{test_connection.id}",
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"] == "test-access-token-12345"
        assert data["token_type"] == "Bearer"
        assert data["connection_id"] == str(test_connection.id)
        assert data["provider"] == test_connection.provider_id

    async def test_get_token_cache_control_header(
        self,
        client: AsyncClient,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
        test_api_key: tuple[ApiKey, str],
    ):
        _api_key, full_key = test_api_key
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens/{test_connection.id}",
            headers={"X-API-Key": full_key},
        )
        assert resp.headers.get("cache-control") == "no-store"

    async def test_get_token_by_provider(
        self,
        client: AsyncClient,
        test_project: Project,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
        test_api_key: tuple[ApiKey, str],
    ):
        _api_key, full_key = test_api_key
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            params={"provider": test_connection.provider_id},
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "test-access-token-12345"

    async def test_get_token_invalid_api_key(
        self,
        client: AsyncClient,
        test_project: Project,
        test_connection: OAuthConnection,
    ):
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens/{test_connection.id}",
            headers={"X-API-Key": "oau_live_invalid"},
        )
        assert resp.status_code == 401

    async def test_get_token_no_connection(
        self,
        client: AsyncClient,
        test_project: Project,
        test_api_key: tuple[ApiKey, str],
    ):
        _api_key, full_key = test_api_key
        fake_conn = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens/{fake_conn}",
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 404

    async def test_get_token_no_provider_match(
        self,
        client: AsyncClient,
        test_project: Project,
        test_api_key: tuple[ApiKey, str],
    ):
        _api_key, full_key = test_api_key
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/tokens",
            params={"provider": "nonexistent"},
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 404

    async def test_get_token_wrong_project(
        self,
        client: AsyncClient,
        test_connection: OAuthConnection,
        test_token_vault: TokenVault,
        test_api_key: tuple[ApiKey, str],
    ):
        _api_key, full_key = test_api_key
        wrong_project = str(uuid.uuid4())
        resp = await client.get(
            f"/api/v1/projects/{wrong_project}/tokens/{test_connection.id}",
            headers={"X-API-Key": full_key},
        )
        assert resp.status_code == 403
