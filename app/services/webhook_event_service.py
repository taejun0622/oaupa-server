"""Fire webhook events to subscribed endpoints."""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


def _sign_payload(payload: str, secret: str) -> str:
    """Create HMAC-SHA256 signature for webhook payload."""
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


async def fire_webhook_event(
    db: AsyncSession,
    project_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Fire a webhook event to all active webhooks subscribed to this event type."""
    result = await db.execute(
        select(Webhook).where(
            Webhook.project_id == project_id,
            Webhook.is_active.is_(True),
        )
    )
    webhooks = result.scalars().all()

    for webhook in webhooks:
        if event_type not in (webhook.events or []):
            continue

        await _deliver_webhook(db, webhook, event_type, payload)


async def _deliver_webhook(
    db: AsyncSession,
    webhook: Webhook,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Deliver a single webhook event and record the delivery."""
    import json

    body = json.dumps({
        "event": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    })

    signature = _sign_payload(body, webhook.secret)

    delivery = WebhookDelivery(
        webhook_id=webhook.id,
        event_type=event_type,
        payload={"event": event_type, "data": payload},
        attempt_count=1,
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                webhook.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Signature": f"sha256={signature}",
                    "X-Webhook-Event": event_type,
                },
            )
        delivery.response_status = response.status_code
        delivery.response_body = response.text[:2048]
        if 200 <= response.status_code < 300:
            delivery.delivered_at = datetime.now(timezone.utc)
    except Exception as e:
        delivery.response_status = 0
        delivery.response_body = str(e)[:2048]
        logger.warning(f"Webhook delivery failed for {webhook.url}: {e}")

    db.add(delivery)
    await db.flush()
