import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.webhook import Webhook, WebhookDelivery


async def list_webhooks(db: AsyncSession, project_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(Webhook).where(Webhook.project_id == project_id)
    )
    return [
        {
            "id": str(wh.id),
            "url": wh.url,
            "events": wh.events,
            "is_active": wh.is_active,
            "created_at": wh.created_at.isoformat() if wh.created_at else None,
        }
        for wh in result.scalars().all()
    ]


async def create_webhook(
    db: AsyncSession, project_id: uuid.UUID, url: str, events: list[str]
) -> dict:
    webhook = Webhook(
        project_id=project_id,
        url=url,
        secret=secrets.token_hex(32),
        events=events,
    )
    db.add(webhook)
    await db.flush()
    return {
        "id": str(webhook.id),
        "url": webhook.url,
        "secret": webhook.secret,
        "events": webhook.events,
        "is_active": webhook.is_active,
    }


async def delete_webhook(
    db: AsyncSession, project_id: uuid.UUID, webhook_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id, Webhook.project_id == project_id
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise NotFoundError("Webhook not found")
    await db.delete(webhook)
    await db.flush()


async def list_deliveries(
    db: AsyncSession, project_id: uuid.UUID, webhook_id: uuid.UUID
) -> list[WebhookDelivery]:
    # Verify webhook belongs to project
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id, Webhook.project_id == project_id
        )
    )
    if result.scalar_one_or_none() is None:
        raise NotFoundError("Webhook not found")

    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(50)
    )
    return list(result.scalars().all())


async def send_test_event(
    db: AsyncSession, project_id: uuid.UUID, webhook_id: uuid.UUID
) -> WebhookDelivery:
    """Send a test webhook event and return the delivery record."""
    result = await db.execute(
        select(Webhook).where(
            Webhook.id == webhook_id, Webhook.project_id == project_id
        )
    )
    webhook = result.scalar_one_or_none()
    if webhook is None:
        raise NotFoundError("Webhook not found")

    from app.services.webhook_event_service import _deliver_webhook

    test_payload = {
        "connection_id": "test-000-000",
        "provider_id": "test_provider",
        "message": "This is a test webhook event",
    }

    await _deliver_webhook(db, webhook, "test.event", test_payload)

    # Get the delivery record we just created
    result = await db.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(1)
    )
    return result.scalar_one()
