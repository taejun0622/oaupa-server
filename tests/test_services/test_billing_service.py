import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.models.subscription import Subscription
from app.models.user import User
from app.services import billing_service


@pytest.mark.asyncio
class TestGetSubscription:
    async def test_free_default(self, db: AsyncSession, test_user: User):
        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "free"
        assert result["status"] == "active"
        assert result["limits"]["connections"] == 3
        assert result["limits"]["token_retrievals"] == 1_000

    async def test_active_subscription(self, db: AsyncSession, test_user: User):
        sub = Subscription(
            user_id=test_user.id,
            stripe_subscription_id=f"sub_{uuid.uuid4().hex[:16]}",
            stripe_price_id="price_test",
            plan_name="pro",
            status="active",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc),
        )
        db.add(sub)
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "pro"
        assert result["status"] == "active"


@pytest.mark.asyncio
class TestEnsureStripeCustomer:
    @patch("app.services.billing_service.stripe")
    async def test_creates_if_missing(self, mock_stripe, db: AsyncSession, test_user: User):
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_new123")
        customer_id = await billing_service._ensure_stripe_customer(db, test_user)
        assert customer_id == "cus_new123"
        assert test_user.stripe_customer_id == "cus_new123"

    async def test_reuses_existing(self, db: AsyncSession, test_user: User):
        test_user.stripe_customer_id = "cus_existing"
        await db.flush()
        customer_id = await billing_service._ensure_stripe_customer(db, test_user)
        assert customer_id == "cus_existing"


@pytest.mark.asyncio
class TestStripeWebhook:
    async def test_invalid_signature(self, db: AsyncSession):
        with pytest.raises(BadRequestError, match="Invalid webhook signature"):
            await billing_service.handle_stripe_webhook(db, b"payload", "bad-sig")

    @patch("app.services.billing_service.stripe")
    async def test_checkout_completed(self, mock_stripe, db: AsyncSession, test_user: User):
        mock_stripe.Webhook.construct_event.return_value = {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "subscription": "sub_test123",
                    "metadata": {"user_id": str(test_user.id), "plan": "starter"},
                }
            },
        }
        mock_stripe.Subscription.retrieve.return_value = {
            "id": "sub_test123",
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }

        result = await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        assert result == {"received": True}

    @patch("app.services.billing_service.stripe")
    async def test_payment_failed(self, mock_stripe, db: AsyncSession, test_user: User):
        # Create subscription first
        sub = Subscription(
            user_id=test_user.id,
            stripe_subscription_id="sub_fail",
            stripe_price_id="price_test",
            plan_name="starter",
            status="active",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc),
        )
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = {
            "type": "invoice.payment_failed",
            "data": {"object": {"subscription": "sub_fail"}},
        }

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        await db.refresh(sub)
        assert sub.status == "past_due"
