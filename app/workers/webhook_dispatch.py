"""Webhook delivery worker with exponential backoff retry."""

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.webhook import Webhook, WebhookDelivery
from app.workers.celery_app import celery_app

MAX_RETRIES = 5
BACKOFF_BASE = 60  # seconds


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(name="app.workers.webhook_dispatch.dispatch_webhook", bind=True, max_retries=5)
def dispatch_webhook(self, delivery_id: str):
    _run_async(_dispatch_webhook(self, delivery_id))


async def _dispatch_webhook(task, delivery_id: str):
    session_factory = _make_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == delivery_id)
        )
        delivery = result.scalar_one_or_none()
        if delivery is None:
            return

        wh_result = await session.execute(
            select(Webhook).where(Webhook.id == delivery.webhook_id)
        )
        webhook = wh_result.scalar_one_or_none()
        if webhook is None or not webhook.is_active:
            return

        payload_json = json.dumps(delivery.payload, default=str)
        signature = hmac.new(
            webhook.secret.encode(), payload_json.encode(), hashlib.sha256
        ).hexdigest()

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    webhook.url,
                    content=payload_json,
                    headers={
                        "Content-Type": "application/json",
                        "X-Oaupa-Signature": signature,
                        "X-Oaupa-Event": delivery.event_type,
                    },
                )
                delivery.response_status = resp.status_code
                delivery.response_body = resp.text[:2000]

                if 200 <= resp.status_code < 300:
                    delivery.delivered_at = datetime.now(timezone.utc)
                else:
                    raise Exception(f"Webhook returned {resp.status_code}")

        except Exception as e:
            delivery.attempt_count += 1
            if delivery.attempt_count < MAX_RETRIES:
                backoff = BACKOFF_BASE * (2 ** (delivery.attempt_count - 1))
                delivery.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff)
                await session.commit()
                task.retry(countdown=backoff, exc=e)
            else:
                delivery.response_body = f"Max retries exceeded: {e}"

        await session.commit()


async def fire_webhook_event(
    session, project_id, event_type: str, payload: dict
):
    """Create webhook deliveries for all matching webhooks in a project."""
    result = await session.execute(
        select(Webhook).where(
            Webhook.project_id == project_id,
            Webhook.is_active.is_(True),
        )
    )
    webhooks = result.scalars().all()

    for webhook in webhooks:
        events = webhook.events
        if event_type not in events and "*" not in events:
            continue

        delivery = WebhookDelivery(
            webhook_id=webhook.id,
            event_type=event_type,
            payload=payload,
        )
        session.add(delivery)
        await session.flush()

        dispatch_webhook.delay(str(delivery.id))
