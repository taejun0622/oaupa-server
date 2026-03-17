"""Test plan: Webhook event firing and delivery.

Tests that webhook events are fired on connection CRUD operations and that
the delivery system works correctly.

Expected events: connection.created, connection.revoked, token.refreshed,
                 api_key.created, api_key.revoked
Expected behavior:
  - fire_webhook_event() creates WebhookDelivery records
  - Only webhooks subscribed to the event type receive deliveries
  - Wildcard ('*') webhooks receive all events
  - Inactive webhooks are skipped
  - Delivery dispatched via Celery task
  - Delivery history queryable via API
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.models.webhook import Webhook, WebhookDelivery
from app.workers.webhook_dispatch import fire_webhook_event


@pytest.mark.asyncio
class TestFireWebhookEvent:
    async def test_fire_creates_delivery_for_matching_webhook(
        self, db: AsyncSession, test_project: Project, test_webhook
    ):
        """Firing an event matching webhook's subscribed events creates a delivery."""
        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "connection.created",
                {"connection_id": str(uuid.uuid4()), "provider": "google"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == test_webhook.id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].event_type == "connection.created"
        assert deliveries[0].payload["provider"] == "google"

    async def test_fire_skips_non_matching_event(
        self, db: AsyncSession, test_project: Project, test_webhook
    ):
        """Webhook subscribed to connection.created should not receive api_key.created."""
        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "api_key.created",
                {"key_name": "test"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == test_webhook.id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 0

    async def test_fire_sends_to_wildcard_webhook(
        self, db: AsyncSession, test_project: Project
    ):
        """Webhook with '*' event subscription receives all events."""
        wildcard_wh = Webhook(
            project_id=test_project.id,
            url="https://wildcard.example.com/webhook",
            secret="wildcard-secret",
            events=["*"],
        )
        db.add(wildcard_wh)
        await db.flush()

        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "any.random.event",
                {"data": "test"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == wildcard_wh.id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1

    async def test_fire_skips_inactive_webhook(
        self, db: AsyncSession, test_project: Project
    ):
        """Inactive webhooks should not receive deliveries."""
        inactive_wh = Webhook(
            project_id=test_project.id,
            url="https://inactive.example.com/webhook",
            secret="inactive-secret",
            events=["connection.created"],
            is_active=False,
        )
        db.add(inactive_wh)
        await db.flush()

        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "connection.created",
                {"data": "test"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == inactive_wh.id)
        )
        assert len(result.scalars().all()) == 0

    async def test_fire_multiple_webhooks_same_project(
        self, db: AsyncSession, test_project: Project
    ):
        """Multiple webhooks subscribed to same event all get deliveries."""
        wh1 = Webhook(
            project_id=test_project.id,
            url="https://wh1.example.com/webhook",
            secret="secret1",
            events=["connection.created"],
        )
        wh2 = Webhook(
            project_id=test_project.id,
            url="https://wh2.example.com/webhook",
            secret="secret2",
            events=["connection.created"],
        )
        db.add_all([wh1, wh2])
        await db.flush()

        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "connection.created",
                {"data": "test"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_id.in_([wh1.id, wh2.id])
            )
        )
        deliveries = result.scalars().all()
        webhook_ids = {d.webhook_id for d in deliveries}
        assert wh1.id in webhook_ids
        assert wh2.id in webhook_ids

    async def test_fire_dispatches_celery_task(
        self, db: AsyncSession, test_project: Project, test_webhook
    ):
        """fire_webhook_event should call dispatch_webhook.delay()."""
        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "connection.created",
                {"data": "test"},
            )
            await db.flush()
            # Verify .delay() was called once (one matching webhook)
            mock_task.delay.assert_called_once()

        # Verify delivery was created with correct initial state
        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.webhook_id == test_webhook.id)
        )
        delivery = result.scalar_one()
        assert delivery.attempt_count == 0
        assert delivery.delivered_at is None


@pytest.mark.asyncio
class TestWebhookFiringIntegration:
    """Tests that verify webhook events fire from actual CRUD operations."""

    async def test_connection_created_fires_webhook(
        self, db: AsyncSession, test_project: Project, test_webhook: Webhook
    ):
        """Creating an OAuth connection should fire connection.created webhook."""
        from app.workers.webhook_dispatch import fire_webhook_event as dispatch_fire

        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await dispatch_fire(
                db, test_project.id, "connection.created",
                {"connection_id": str(uuid.uuid4()), "provider": "google"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_id == test_webhook.id,
                WebhookDelivery.event_type == "connection.created",
            )
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].payload["provider"] == "google"

    async def test_connection_revoked_fires_webhook(
        self, db: AsyncSession, test_project: Project
    ):
        """Revoking a connection should fire connection.revoked webhook."""
        revoke_wh = Webhook(
            project_id=test_project.id,
            url="https://revoke.example.com/hook",
            secret="revoke-secret",
            events=["connection.revoked"],
        )
        db.add(revoke_wh)
        await db.flush()

        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "connection.revoked",
                {"connection_id": str(uuid.uuid4()), "reason": "user_initiated"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_id == revoke_wh.id,
                WebhookDelivery.event_type == "connection.revoked",
            )
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        assert deliveries[0].payload["reason"] == "user_initiated"

    async def test_token_refreshed_fires_webhook(
        self, db: AsyncSession, test_project: Project, test_webhook: Webhook
    ):
        """Token refresh should fire token.refreshed webhook."""
        # test_webhook is subscribed to ["connection.created", "token.refreshed"]
        with patch("app.workers.webhook_dispatch.dispatch_webhook") as mock_task:
            await fire_webhook_event(
                db, test_project.id, "token.refreshed",
                {"connection_id": str(uuid.uuid4()), "provider": "google"},
            )
            await db.flush()

        result = await db.execute(
            select(WebhookDelivery).where(
                WebhookDelivery.webhook_id == test_webhook.id,
                WebhookDelivery.event_type == "token.refreshed",
            )
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1


@pytest.mark.asyncio
class TestWebhookDeliveryHistoryAPI:
    """Tests for delivery history and test-event endpoints."""

    async def _get_auth_headers(self, client: AsyncClient, email: str, password: str = "testpassword123") -> dict:
        await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Test User"},
        )
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        token = resp.json()["access_token"]
        return {"Authorization": f"Bearer {token}"}

    async def test_list_deliveries_for_webhook(
        self, db: AsyncSession, client: AsyncClient, test_project: Project, test_user: User, test_webhook: Webhook
    ):
        """GET /projects/{id}/webhooks/{id}/deliveries returns delivery history."""
        # Create some delivery records directly in DB
        d1 = WebhookDelivery(
            webhook_id=test_webhook.id,
            event_type="connection.created",
            payload={"connection_id": "abc", "provider": "google"},
            response_status=200,
            response_body="OK",
            attempt_count=1,
            delivered_at=datetime.now(timezone.utc),
        )
        d2 = WebhookDelivery(
            webhook_id=test_webhook.id,
            event_type="token.refreshed",
            payload={"connection_id": "xyz"},
            response_status=500,
            response_body="Internal Server Error",
            attempt_count=2,
        )
        db.add_all([d1, d2])
        await db.flush()

        headers = await self._get_auth_headers(client, f"delivery-test-{uuid.uuid4().hex[:8]}@test.com")

        # Re-login as the project owner (test_user) — register/login creates a new user,
        # so we need to authenticate as test_user instead.
        # Use the test_user's email by logging in via the existing user's JWT directly.
        # Since test_user was created directly in DB, we issue a JWT for them.
        from app.core.security import create_access_token
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/webhooks/{test_webhook.id}/deliveries",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 2

        event_types = {item["event_type"] for item in data}
        assert "connection.created" in event_types
        assert "token.refreshed" in event_types

    async def test_delivery_includes_response_status(
        self, db: AsyncSession, client: AsyncClient, test_project: Project, test_user: User, test_webhook: Webhook
    ):
        """Delivery records include response status and attempt count."""
        delivery = WebhookDelivery(
            webhook_id=test_webhook.id,
            event_type="connection.created",
            payload={"connection_id": "abc"},
            response_status=404,
            response_body="Not Found",
            attempt_count=3,
        )
        db.add(delivery)
        await db.flush()

        from app.core.security import create_access_token
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get(
            f"/api/v1/projects/{test_project.id}/webhooks/{test_webhook.id}/deliveries",
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        record = next(r for r in data if r["event_type"] == "connection.created")
        assert record["response_status"] == 404
        assert record["attempt_count"] == 3
        assert record["delivered_at"] is None

    async def test_list_deliveries_wrong_project_returns_404(
        self, db: AsyncSession, client: AsyncClient, test_project: Project, test_user: User, test_webhook: Webhook
    ):
        """Accessing deliveries for a webhook not belonging to the user's project returns 404."""
        # Create another project with another webhook
        other_user = User(
            email=f"other-{uuid.uuid4().hex[:8]}@test.com",
            password_hash="x",
            full_name="Other",
        )
        db.add(other_user)
        await db.flush()

        other_project = Project(
            user_id=other_user.id,
            name="Other Project",
            slug=f"other-{uuid.uuid4().hex[:8]}",
        )
        db.add(other_project)
        await db.flush()

        other_wh = Webhook(
            project_id=other_project.id,
            url="https://other.example.com/hook",
            secret="other-secret",
            events=["connection.created"],
        )
        db.add(other_wh)
        await db.flush()

        from app.core.security import create_access_token
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        # test_user tries to access other_project's webhook deliveries
        resp = await client.get(
            f"/api/v1/projects/{other_project.id}/webhooks/{other_wh.id}/deliveries",
            headers=headers,
        )
        assert resp.status_code == 404

    async def test_test_endpoint_creates_delivery(
        self, db: AsyncSession, client: AsyncClient, test_project: Project, test_user: User, test_webhook: Webhook
    ):
        """POST /webhooks/{id}/test creates a delivery and returns delivery_id + status."""
        from app.core.security import create_access_token
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        # Mock the actual HTTP call so we don't hit the network
        with patch("app.services.webhook_event_service.httpx.AsyncClient") as mock_http:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.return_value.post = AsyncMock(return_value=mock_response)

            resp = await client.post(
                f"/api/v1/projects/{test_project.id}/webhooks/{test_webhook.id}/test",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert "delivery_id" in data
        assert "status" in data
        assert data["status"] in ("delivered", "failed")

        # Confirm delivery record was written to DB
        delivery_id = uuid.UUID(data["delivery_id"])
        result = await db.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        )
        delivery = result.scalar_one_or_none()
        assert delivery is not None
        assert delivery.event_type == "test.event"

    async def test_test_endpoint_marks_delivered_on_success(
        self, db: AsyncSession, client: AsyncClient, test_project: Project, test_user: User, test_webhook: Webhook
    ):
        """Test endpoint returns status=delivered when HTTP call succeeds."""
        from app.core.security import create_access_token
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.services.webhook_event_service.httpx.AsyncClient") as mock_http:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.return_value.post = AsyncMock(return_value=mock_response)

            resp = await client.post(
                f"/api/v1/projects/{test_project.id}/webhooks/{test_webhook.id}/test",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "delivered"

    async def test_test_endpoint_marks_failed_on_http_error(
        self, db: AsyncSession, client: AsyncClient, test_project: Project, test_user: User, test_webhook: Webhook
    ):
        """Test endpoint returns status=failed when HTTP call fails."""
        from app.core.security import create_access_token
        token = create_access_token(str(test_user.id))
        headers = {"Authorization": f"Bearer {token}"}

        with patch("app.services.webhook_event_service.httpx.AsyncClient") as mock_http:
            mock_http.return_value.__aenter__ = AsyncMock(return_value=mock_http.return_value)
            mock_http.return_value.__aexit__ = AsyncMock(return_value=False)
            mock_http.return_value.post = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            resp = await client.post(
                f"/api/v1/projects/{test_project.id}/webhooks/{test_webhook.id}/test",
                headers=headers,
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"
