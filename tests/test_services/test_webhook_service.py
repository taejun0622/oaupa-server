import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.models.webhook import Webhook
from app.services import webhook_service


@pytest.mark.asyncio
class TestCreateWebhook:
    async def test_success(self, db: AsyncSession, test_project: Project):
        result = await webhook_service.create_webhook(
            db, test_project.id, "https://example.com/hook", ["connection.created"]
        )
        assert result["url"] == "https://example.com/hook"
        assert "secret" in result
        assert len(result["secret"]) == 64  # hex(32 bytes)
        assert result["events"] == ["connection.created"]
        assert result["is_active"] is True


@pytest.mark.asyncio
class TestListWebhooks:
    async def test_returns_project_webhooks(
        self, db: AsyncSession, test_project: Project, test_webhook: Webhook
    ):
        result = await webhook_service.list_webhooks(db, test_project.id)
        assert len(result) >= 1
        assert any(w["id"] == str(test_webhook.id) for w in result)

    async def test_empty_for_other_project(self, db: AsyncSession):
        result = await webhook_service.list_webhooks(db, uuid.uuid4())
        assert result == []


@pytest.mark.asyncio
class TestDeleteWebhook:
    async def test_success(self, db: AsyncSession, test_project: Project):
        result = await webhook_service.create_webhook(
            db, test_project.id, "https://example.com/del", ["*"]
        )
        webhook_id = uuid.UUID(result["id"])
        await webhook_service.delete_webhook(db, test_project.id, webhook_id)

        # Should not appear in list
        webhooks = await webhook_service.list_webhooks(db, test_project.id)
        ids = [w["id"] for w in webhooks]
        assert str(webhook_id) not in ids

    async def test_not_found(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await webhook_service.delete_webhook(db, test_project.id, uuid.uuid4())

    async def test_wrong_project(
        self, db: AsyncSession, test_project: Project, test_webhook: Webhook
    ):
        with pytest.raises(NotFoundError):
            await webhook_service.delete_webhook(db, uuid.uuid4(), test_webhook.id)
