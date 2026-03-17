import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.models.webhook import Webhook
from tests.conftest import auth_headers, create_project_via_api


@pytest.mark.asyncio
class TestWebhooks:
    async def test_create_webhook(
        self,
        client: AsyncClient,
        test_user: User,
        test_project: Project,
    ):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.post(
            f"/api/v1/projects/{test_project.id}/webhooks",
            json={"url": "https://example.com/hook", "events": ["connection.created"]},
            headers=headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "secret" in data
        assert data["url"] == "https://example.com/hook"

    async def test_list_webhooks(
        self,
        client: AsyncClient,
        test_user: User,
        test_project: Project,
        test_webhook: Webhook,
    ):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/webhooks",
            headers=headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1

    async def test_delete_webhook(
        self,
        client: AsyncClient,
        test_user: User,
        test_project: Project,
        test_webhook: Webhook,
    ):
        from app.core.security import create_access_token

        headers = {"Authorization": f"Bearer {create_access_token(str(test_user.id))}"}
        resp = await client.delete(
            f"/api/v1/projects/{test_project.id}/webhooks/{test_webhook.id}",
            headers=headers,
        )
        assert resp.status_code == 204
