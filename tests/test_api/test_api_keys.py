import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, create_api_key_via_api, create_project_via_api


@pytest.mark.asyncio
class TestApiKeys:
    async def test_create_api_key(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/api-keys",
            json={"name": "Production"},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "full_key" in data
        assert data["full_key"].startswith("oau_live_")
        assert data["name"] == "Production"
        assert data["is_active"] is True

    async def test_create_api_key_with_scopes(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/api-keys",
            json={"name": "ReadOnly", "scopes": ["tokens:read"]},
            headers=headers,
        )
        assert resp.status_code == 201
        assert resp.json()["scopes"] == ["tokens:read"]

    async def test_list_api_keys_no_full_key(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        await client.post(
            f"/api/v1/projects/{project['id']}/api-keys",
            json={"name": "Key1"},
            headers=headers,
        )
        resp = await client.get(
            f"/api/v1/projects/{project['id']}/api-keys",
            headers=headers,
        )
        assert resp.status_code == 200
        keys = resp.json()
        assert len(keys) >= 1
        # full_key should NOT be in list response
        for key in keys:
            assert "full_key" not in key

    async def test_revoke_api_key(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        create_resp = await client.post(
            f"/api/v1/projects/{project['id']}/api-keys",
            json={"name": "ToRevoke"},
            headers=headers,
        )
        key_id = create_resp.json()["id"]
        resp = await client.delete(
            f"/api/v1/projects/{project['id']}/api-keys/{key_id}",
            headers=headers,
        )
        assert resp.status_code == 204

        # Revoked key should not appear in active list
        list_resp = await client.get(
            f"/api/v1/projects/{project['id']}/api-keys",
            headers=headers,
        )
        ids = [k["id"] for k in list_resp.json()]
        assert key_id not in ids
