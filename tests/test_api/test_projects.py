import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers, create_project_via_api


@pytest.mark.asyncio
class TestProjects:
    async def test_create_project(self, client: AsyncClient):
        headers = await auth_headers(client)
        slug = f"test-{uuid.uuid4().hex[:8]}"
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "My Project", "slug": slug},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Project"
        assert data["slug"] == slug

    async def test_create_project_duplicate_slug(self, client: AsyncClient):
        headers = await auth_headers(client)
        slug = f"dup-{uuid.uuid4().hex[:8]}"
        await client.post(
            "/api/v1/projects",
            json={"name": "P1", "slug": slug},
            headers=headers,
        )
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "P2", "slug": slug},
            headers=headers,
        )
        assert resp.status_code == 409

    async def test_list_projects(self, client: AsyncClient):
        headers = await auth_headers(client)
        await create_project_via_api(client, headers)
        await create_project_via_api(client, headers)
        resp = await client.get("/api/v1/projects", headers=headers)
        assert resp.status_code == 200
        assert len(resp.json()) >= 2

    async def test_get_project(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        resp = await client.get(f"/api/v1/projects/{project['id']}", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["id"] == project["id"]

    async def test_get_other_users_project(self, client: AsyncClient):
        headers1 = await auth_headers(client)
        project = await create_project_via_api(client, headers1)
        headers2 = await auth_headers(client)
        resp = await client.get(f"/api/v1/projects/{project['id']}", headers=headers2)
        assert resp.status_code == 404

    async def test_update_project(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        resp = await client.patch(
            f"/api/v1/projects/{project['id']}",
            json={"name": "Renamed"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"

    async def test_delete_project(self, client: AsyncClient):
        headers = await auth_headers(client)
        project = await create_project_via_api(client, headers)
        resp = await client.delete(f"/api/v1/projects/{project['id']}", headers=headers)
        assert resp.status_code == 204

        # Should not appear in list anymore
        resp = await client.get("/api/v1/projects", headers=headers)
        ids = [p["id"] for p in resp.json()]
        assert project["id"] not in ids

    async def test_create_project_unauthenticated(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "X", "slug": "x"},
        )
        assert resp.status_code in (401, 422)
