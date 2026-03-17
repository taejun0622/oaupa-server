"""Stripe billing integration."""

import uuid
from datetime import date, datetime, timezone
from functools import partial
from typing import Any

import anyio
import stripe
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.models.project import Project
from app.models.subscription import Subscription
from app.models.usage import UsageRecord
from app.models.user import User

stripe.api_key = settings.stripe_secret_key

PLAN_PRICES = {
    "free": settings.stripe_price_free,
    "starter": settings.stripe_price_starter,
    "pro": settings.stripe_price_pro,
}

PLAN_LIMITS = {
    "free": {"connections": 3, "token_retrievals": 1_000},
    "starter": {"connections": 20, "token_retrievals": 50_000},
    "pro": {"connections": 100, "token_retrievals": 500_000},
    "enterprise": {"connections": float("inf"), "token_retrievals": float("inf")},
}

# Reverse lookup: price_id → plan_name
PRICE_TO_PLAN = {v: k for k, v in PLAN_PRICES.items() if v}


async def _run_stripe(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Run a synchronous Stripe API call in a thread to avoid blocking the event loop."""
    return await anyio.to_thread.run_sync(partial(fn, *args, **kwargs))


async def _ensure_stripe_customer(db: AsyncSession, user: User) -> str:
    if user.stripe_customer_id:
        return user.stripe_customer_id

    customer = await _run_stripe(
        stripe.Customer.create,
        email=user.email,
        name=user.full_name,
        metadata={"user_id": str(user.id)},
    )
    user.stripe_customer_id = customer.id
    await db.flush()
    return customer.id


async def _get_active_subscription(db: AsyncSession, user_id: uuid.UUID) -> Subscription | None:
    result = await db.execute(
        select(Subscription)
        .where(
            Subscription.user_id == user_id,
            Subscription.status.in_(["active", "trialing", "past_due"]),
        )
        .order_by(Subscription.current_period_end.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_plan_name(db: AsyncSession, user: User) -> str:
    sub = await _get_active_subscription(db, user.id)
    return sub.plan_name if sub else "free"


async def get_subscription(db: AsyncSession, user: User) -> dict:
    sub = await _get_active_subscription(db, user.id)
    if sub is None:
        return {"plan": "free", "status": "active", "limits": PLAN_LIMITS["free"]}

    return {
        "plan": sub.plan_name,
        "status": sub.status,
        "current_period_end": sub.current_period_end.isoformat(),
        "cancel_at_period_end": sub.cancel_at_period_end,
        "limits": PLAN_LIMITS.get(sub.plan_name, PLAN_LIMITS["free"]),
    }


async def check_connection_limit(db: AsyncSession, user: User) -> None:
    """Raise ForbiddenError if user has reached their plan's connection limit."""
    plan = await get_plan_name(db, user)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    max_connections = limits["connections"]

    if max_connections == float("inf"):
        return

    from app.models.oauth_connection import OAuthConnection

    result = await db.execute(
        select(func.count())
        .select_from(OAuthConnection)
        .join(Project, OAuthConnection.project_id == Project.id)
        .where(
            Project.user_id == user.id,
            OAuthConnection.status == "active",
        )
    )
    current_count = result.scalar_one()

    if current_count >= max_connections:
        raise ForbiddenError(
            f"Connection limit reached ({int(max_connections)} on {plan} plan). "
            "Upgrade your plan to add more connections."
        )


async def check_retrieval_limit(db: AsyncSession, user: User) -> None:
    """Raise ForbiddenError if user has exceeded their plan's token retrieval limit for the current period."""
    plan = await get_plan_name(db, user)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])
    max_retrievals = limits["token_retrievals"]

    if max_retrievals == float("inf"):
        return

    today = date.today()
    period_start = today.replace(day=1)

    result = await db.execute(
        select(func.coalesce(func.sum(UsageRecord.token_retrievals), 0))
        .join(Project, UsageRecord.project_id == Project.id)
        .where(
            Project.user_id == user.id,
            UsageRecord.period_start >= period_start,
        )
    )
    current_count = result.scalar_one()

    if current_count >= max_retrievals:
        raise ForbiddenError(
            f"Token retrieval limit reached ({int(max_retrievals)} on {plan} plan). "
            "Upgrade your plan for more retrievals."
        )


async def track_token_retrieval(db: AsyncSession, project_id: uuid.UUID) -> None:
    """Increment the token retrieval counter for the current billing period."""
    today = date.today()
    period_start = today.replace(day=1)

    result = await db.execute(
        select(UsageRecord).where(
            UsageRecord.project_id == project_id,
            UsageRecord.period_start == period_start,
        )
    )
    record = result.scalar_one_or_none()

    if record is None:
        record = UsageRecord(
            project_id=project_id,
            period_start=period_start,
            token_retrievals=1,
            connections_count=0,
        )
        db.add(record)
    else:
        record.token_retrievals += 1

    await db.flush()


async def create_checkout_session(db: AsyncSession, user: User, plan: str) -> dict:
    price_id = PLAN_PRICES.get(plan)
    if not price_id:
        raise BadRequestError(f"Unknown plan: {plan}")

    customer_id = await _ensure_stripe_customer(db, user)

    session = await _run_stripe(
        stripe.checkout.Session.create,
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{settings.cors_origins[0]}/billing?success=true",
        cancel_url=f"{settings.cors_origins[0]}/billing?canceled=true",
        metadata={"user_id": str(user.id), "plan": plan},
    )
    return {"checkout_url": session.url}


async def create_portal_session(db: AsyncSession, user: User) -> dict:
    customer_id = await _ensure_stripe_customer(db, user)
    session = await _run_stripe(
        stripe.billing_portal.Session.create,
        customer=customer_id,
        return_url=f"{settings.cors_origins[0]}/billing",
    )
    return {"portal_url": session.url}


async def get_usage(db: AsyncSession, user: User) -> dict:
    plan = await get_plan_name(db, user)
    limits = PLAN_LIMITS.get(plan, PLAN_LIMITS["free"])

    today = date.today()
    period_start = today.replace(day=1)

    result = await db.execute(
        select(
            func.coalesce(func.sum(UsageRecord.token_retrievals), 0),
            func.coalesce(func.sum(UsageRecord.connections_count), 0),
        )
        .join(Project, UsageRecord.project_id == Project.id)
        .where(
            Project.user_id == user.id,
            UsageRecord.period_start >= period_start,
        )
    )
    row = result.one()
    token_retrievals = row[0]
    connections_count = row[1]

    # Generate warnings at 80%+ of limits
    warnings = []
    max_retrievals = limits["token_retrievals"]
    max_connections = limits["connections"]

    if max_retrievals != float("inf") and max_retrievals > 0:
        pct = token_retrievals / max_retrievals
        if pct >= 1.0:
            warnings.append(f"Token retrieval limit reached ({token_retrievals}/{int(max_retrievals)})")
        elif pct >= 0.8:
            warnings.append(f"Approaching token retrieval limit ({token_retrievals}/{int(max_retrievals)})")

    if max_connections != float("inf") and max_connections > 0:
        # Count actual active connections
        from app.models.oauth_connection import OAuthConnection
        conn_result = await db.execute(
            select(func.count())
            .select_from(OAuthConnection)
            .join(Project, OAuthConnection.project_id == Project.id)
            .where(Project.user_id == user.id, OAuthConnection.status == "active")
        )
        active_connections = conn_result.scalar_one()
        conn_pct = active_connections / max_connections
        if conn_pct >= 1.0:
            warnings.append(f"Connection limit reached ({active_connections}/{int(max_connections)})")
        elif conn_pct >= 0.8:
            warnings.append(f"Approaching connection limit ({active_connections}/{int(max_connections)})")

    return {
        "token_retrievals": token_retrievals,
        "connections_count": connections_count,
        "limits": limits,
        "warnings": warnings,
    }


async def get_invoices(db: AsyncSession, user: User) -> list[dict]:
    """Fetch invoice history from Stripe for the user's customer."""
    if not user.stripe_customer_id:
        return []

    invoices = await _run_stripe(
        stripe.Invoice.list,
        customer=user.stripe_customer_id,
        limit=20,
    )

    return [
        {
            "id": inv["id"],
            "amount_due": inv["amount_due"],
            "amount_paid": inv["amount_paid"],
            "currency": inv["currency"],
            "status": inv.get("status"),
            "period_start": datetime.fromtimestamp(inv["period_start"], tz=timezone.utc).isoformat() if inv.get("period_start") else None,
            "period_end": datetime.fromtimestamp(inv["period_end"], tz=timezone.utc).isoformat() if inv.get("period_end") else None,
            "invoice_url": inv.get("hosted_invoice_url"),
            "created": datetime.fromtimestamp(inv["created"], tz=timezone.utc).isoformat() if inv.get("created") else None,
        }
        for inv in invoices.get("data", [])
    ]


async def handle_stripe_webhook(db: AsyncSession, payload: bytes, sig: str) -> dict:
    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except (ValueError, stripe.SignatureVerificationError):
        raise BadRequestError("Invalid webhook signature")

    event_id = event["id"]
    event_type = event["type"]
    data = event["data"]["object"]

    # Idempotency: skip already-processed events
    from app.models.stripe_event import StripeEvent
    existing = await db.execute(
        select(StripeEvent).where(StripeEvent.event_id == event_id)
    )
    if existing.scalar_one_or_none() is not None:
        return {"received": True}

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(db, data)
    elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
        await _handle_subscription_update(db, data)
    elif event_type == "invoice.payment_failed":
        await _handle_payment_failed(db, data)
    elif event_type == "invoice.payment_succeeded":
        await _handle_payment_succeeded(db, data)

    # Record processed event
    db.add(StripeEvent(event_id=event_id, event_type=event_type))
    await db.flush()

    return {"received": True}


async def _handle_checkout_completed(db: AsyncSession, data: dict) -> None:
    subscription_id = data.get("subscription")
    if not subscription_id:
        return

    stripe_sub = await _run_stripe(stripe.Subscription.retrieve, subscription_id)
    user_id = data.get("metadata", {}).get("user_id")
    plan = data.get("metadata", {}).get("plan", "starter")

    if not user_id:
        return

    # Upsert with row lock to prevent race conditions
    result = await db.execute(
        select(Subscription)
        .where(Subscription.stripe_subscription_id == stripe_sub["id"])
        .with_for_update()
    )
    sub = result.scalar_one_or_none()

    if sub is None:
        sub = Subscription(
            user_id=uuid.UUID(user_id),
            stripe_subscription_id=stripe_sub["id"],
            stripe_price_id=stripe_sub["items"]["data"][0]["price"]["id"],
            plan_name=plan,
            status=stripe_sub["status"],
            current_period_start=datetime.fromtimestamp(stripe_sub["current_period_start"], tz=timezone.utc),
            current_period_end=datetime.fromtimestamp(stripe_sub["current_period_end"], tz=timezone.utc),
        )
        db.add(sub)
    else:
        sub.stripe_price_id = stripe_sub["items"]["data"][0]["price"]["id"]
        sub.plan_name = plan
        sub.status = stripe_sub["status"]
        sub.current_period_start = datetime.fromtimestamp(stripe_sub["current_period_start"], tz=timezone.utc)
        sub.current_period_end = datetime.fromtimestamp(stripe_sub["current_period_end"], tz=timezone.utc)

    await db.flush()


async def _handle_subscription_update(db: AsyncSession, data: dict) -> None:
    result = await db.execute(
        select(Subscription)
        .where(Subscription.stripe_subscription_id == data["id"])
        .with_for_update()
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        return

    sub.status = data["status"]
    sub.cancel_at_period_end = data.get("cancel_at_period_end", False)
    if data.get("current_period_start"):
        sub.current_period_start = datetime.fromtimestamp(data["current_period_start"], tz=timezone.utc)
    if data.get("current_period_end"):
        sub.current_period_end = datetime.fromtimestamp(data["current_period_end"], tz=timezone.utc)

    # Detect plan change (upgrade/downgrade via portal)
    items = data.get("items", {}).get("data", [])
    if items:
        new_price_id = items[0].get("price", {}).get("id")
        if new_price_id and new_price_id != sub.stripe_price_id:
            sub.stripe_price_id = new_price_id
            sub.plan_name = PRICE_TO_PLAN.get(new_price_id, sub.plan_name)

    await db.flush()


async def _handle_payment_failed(db: AsyncSession, data: dict) -> None:
    subscription_id = data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(Subscription)
        .where(Subscription.stripe_subscription_id == subscription_id)
        .with_for_update()
    )
    sub = result.scalar_one_or_none()
    if sub:
        sub.status = "past_due"
        await db.flush()


async def _handle_payment_succeeded(db: AsyncSession, data: dict) -> None:
    subscription_id = data.get("subscription")
    if not subscription_id:
        return

    result = await db.execute(
        select(Subscription)
        .where(Subscription.stripe_subscription_id == subscription_id)
        .with_for_update()
    )
    sub = result.scalar_one_or_none()
    if sub and sub.status == "past_due":
        sub.status = "active"
        await db.flush()
