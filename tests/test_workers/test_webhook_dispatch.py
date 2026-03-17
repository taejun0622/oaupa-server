import hashlib
import hmac
import json
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.webhook import Webhook, WebhookDelivery


@pytest.mark.asyncio
class TestHMACSignature:
    def test_signature_generation(self):
        secret = "my-webhook-secret"
        payload = json.dumps({"event": "test", "data": {"id": "123"}})
        sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        # Verify it's a valid hex string
        assert len(sig) == 64
        # Verify it's deterministic
        sig2 = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        assert sig == sig2

    def test_different_secrets_different_sigs(self):
        payload = json.dumps({"test": True})
        sig1 = hmac.new(b"secret1", payload.encode(), hashlib.sha256).hexdigest()
        sig2 = hmac.new(b"secret2", payload.encode(), hashlib.sha256).hexdigest()
        assert sig1 != sig2


@pytest.mark.asyncio
class TestFireWebhookEvent:
    async def test_creates_delivery_for_matching_event(
        self, db: AsyncSession, test_project: Project, test_webhook: Webhook
    ):
        from unittest.mock import patch
        from app.workers.webhook_dispatch import fire_webhook_event

        # test_webhook events: ["connection.created", "token.refreshed"]
        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            mock_task.delay = lambda *a, **kw: None
            await fire_webhook_event(
                db, test_project.id, "connection.created", {"connection_id": "abc"}
            )

        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == test_webhook.id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) >= 1
        assert deliveries[-1].event_type == "connection.created"
        assert deliveries[-1].payload == {"connection_id": "abc"}

    async def test_skips_non_matching_event(
        self, db: AsyncSession, test_project: Project, test_webhook: Webhook
    ):
        from unittest.mock import patch
        from app.workers.webhook_dispatch import fire_webhook_event

        # Count existing deliveries
        result_before = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == test_webhook.id)
        )
        count_before = len(result_before.scalars().all())

        # "user.deleted" is not in test_webhook.events
        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            mock_task.delay = lambda *a, **kw: None
            await fire_webhook_event(
                db, test_project.id, "user.deleted", {"user_id": "123"}
            )

        result_after = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == test_webhook.id)
        )
        count_after = len(result_after.scalars().all())
        assert count_after == count_before

    async def test_wildcard_event_matches_all(
        self, db: AsyncSession, test_project: Project
    ):
        from unittest.mock import patch
        from app.workers.webhook_dispatch import fire_webhook_event

        wildcard_webhook = Webhook(
            project_id=test_project.id,
            url="https://example.com/wildcard",
            secret="wildcard-secret",
            events=["*"],
        )
        db.add(wildcard_webhook)
        await db.flush()

        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            mock_task.delay = lambda *a, **kw: None
            await fire_webhook_event(
                db, test_project.id, "anything.at.all", {"data": "value"}
            )

        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == wildcard_webhook.id)
        )
        assert len(result.scalars().all()) >= 1
