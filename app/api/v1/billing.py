from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.billing import (
    BillingConfigResponse,
    CheckoutRequest,
    CheckoutResponse,
    InvoiceResponse,
    PlanLimits,
    PortalResponse,
    SubscriptionResponse,
    UsageResponse,
    StripeWebhookResponse,
)

router = APIRouter()


@router.get("/config", response_model=BillingConfigResponse)
async def get_billing_config():
    from app.config import settings
    from app.services.billing_service import PLAN_LIMITS
    return {
        "stripe_publishable_key": settings.stripe_publishable_key,
        "plans": {k: PlanLimits(**v) for k, v in PLAN_LIMITS.items()},
    }


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services import billing_service
    return await billing_service.get_subscription(db, user)


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    body: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services import billing_service
    return await billing_service.create_checkout_session(db, user, body.plan)


@router.post("/portal", response_model=PortalResponse)
async def create_portal(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services import billing_service
    return await billing_service.create_portal_session(db, user)


@router.get("/usage", response_model=UsageResponse)
async def get_usage(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services import billing_service
    return await billing_service.get_usage(db, user)


@router.get("/invoices", response_model=list[InvoiceResponse])
async def get_invoices(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services import billing_service
    return await billing_service.get_invoices(db, user)


@router.post("/webhooks/stripe", response_model=StripeWebhookResponse)
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    from app.services import billing_service
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    return await billing_service.handle_stripe_webhook(db, payload, sig)
