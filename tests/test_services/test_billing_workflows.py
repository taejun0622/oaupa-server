"""Payment workflow edge case tests.

Covers: subscription lifecycle, webhook ordering, downgrade edge cases,
concurrent limits, Stripe API failures, and deleted user scenarios.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ForbiddenError
from app.models.oauth_connection import OAuthConnection
from app.models.project import Project
from app.models.stripe_event import StripeEvent
from app.models.subscription import Subscription
from app.models.usage import UsageRecord
from app.models.user import User
from app.services import billing_service


# ── Helpers ──────────────────────────────────────────────────────────


def _make_sub(user: User, plan: str = "starter", status: str = "active", **kw) -> Subscription:
    return Subscription(
        user_id=user.id,
        stripe_subscription_id=kw.get("sub_id", f"sub_{uuid.uuid4().hex[:16]}"),
        stripe_price_id=f"price_{plan}",
        plan_name=plan,
        status=status,
        current_period_start=kw.get("period_start", datetime.now(timezone.utc)),
        current_period_end=kw.get("period_end", datetime.now(timezone.utc) + timedelta(days=30)),
        cancel_at_period_end=kw.get("cancel_at_period_end", False),
    )


def _make_connection(project: Project, user: User, provider_id: str, status: str = "active") -> OAuthConnection:
    return OAuthConnection(
        project_id=project.id,
        user_id=user.id,
        provider_id=provider_id,
        provider_account_id=f"acct-{uuid.uuid4().hex[:8]}",
        scopes_granted=["read"],
        status=status,
    )


def _webhook_event(event_type: str, data: dict, event_id: str | None = None) -> dict:
    return {
        "id": event_id or f"evt_{uuid.uuid4().hex[:16]}",
        "type": event_type,
        "data": {"object": data},
    }


# ── Subscription Lifecycle ──────────────────────────────────────────


@pytest.mark.asyncio
class TestSubscriptionLifecycle:
    async def test_free_to_starter_via_checkout_webhook(
        self, db: AsyncSession, test_user: User
    ):
        """Full lifecycle: free user → checkout.session.completed → becomes starter."""
        assert await billing_service.get_plan_name(db, test_user) == "free"

        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "checkout.session.completed",
                {
                    "subscription": sub_id,
                    "metadata": {"user_id": str(test_user.id), "plan": "starter"},
                },
            )
            mock_stripe.Subscription.retrieve.return_value = {
                "id": sub_id,
                "status": "active",
                "current_period_start": 1700000000,
                "current_period_end": 1702592000,
                "items": {"data": [{"price": {"id": "price_starter"}}]},
            }
            await billing_service.handle_stripe_webhook(db, b"p", "s")

        assert await billing_service.get_plan_name(db, test_user) == "starter"

    async def test_upgrade_starter_to_pro_via_subscription_update(
        self, db: AsyncSession, test_user: User
    ):
        """Starter → Pro upgrade via Stripe portal triggers subscription.updated."""
        sub = _make_sub(test_user, plan="starter")
        sub.stripe_price_id = "price_starter"
        db.add(sub)
        await db.flush()

        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "customer.subscription.updated",
                {
                    "id": sub.stripe_subscription_id,
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                    "items": {"data": [{"price": {"id": "price_pro"}}]},
                },
            )
            with patch.dict(billing_service.PRICE_TO_PLAN, {"price_pro": "pro"}):
                await billing_service.handle_stripe_webhook(db, b"p", "s")

        await db.refresh(sub)
        assert sub.plan_name == "pro"
        assert sub.stripe_price_id == "price_pro"

    async def test_downgrade_pro_to_starter_via_portal(
        self, db: AsyncSession, test_user: User
    ):
        """Downgrade: subscription.updated changes price_id from pro to starter."""
        sub = _make_sub(test_user, plan="pro")
        sub.stripe_price_id = "price_pro"
        db.add(sub)
        await db.flush()

        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "customer.subscription.updated",
                {
                    "id": sub.stripe_subscription_id,
                    "status": "active",
                    "cancel_at_period_end": False,
                    "current_period_start": 1700000000,
                    "current_period_end": 1702592000,
                    "items": {"data": [{"price": {"id": "price_starter"}}]},
                },
            )
            with patch.dict(billing_service.PRICE_TO_PLAN, {"price_starter": "starter"}):
                await billing_service.handle_stripe_webhook(db, b"p", "s")

        await db.refresh(sub)
        assert sub.plan_name == "starter"

    async def test_cancel_then_delete_lifecycle(
        self, db: AsyncSession, test_user: User
    ):
        """Active → cancel_at_period_end → subscription.deleted → falls to free."""
        sub = _make_sub(test_user, plan="pro")
        db.add(sub)
        await db.flush()

        # Step 1: User cancels via portal → subscription.updated with cancel_at_period_end
        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "customer.subscription.updated",
                {
                    "id": sub.stripe_subscription_id,
                    "status": "active",
                    "cancel_at_period_end": True,
                },
            )
            await billing_service.handle_stripe_webhook(db, b"p", "s")

        await db.refresh(sub)
        assert sub.cancel_at_period_end is True
        assert sub.status == "active"
        # Still on pro
        assert await billing_service.get_plan_name(db, test_user) == "pro"

        # Step 2: Period ends → subscription.deleted
        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "customer.subscription.deleted",
                {
                    "id": sub.stripe_subscription_id,
                    "status": "canceled",
                    "cancel_at_period_end": False,
                },
            )
            await billing_service.handle_stripe_webhook(db, b"p", "s")

        await db.refresh(sub)
        assert sub.status == "canceled"
        # Falls to free
        assert await billing_service.get_plan_name(db, test_user) == "free"

    async def test_payment_failure_recovery_lifecycle(
        self, db: AsyncSession, test_user: User
    ):
        """Active → payment fails → past_due → user updates card → payment succeeds → active."""
        sub = _make_sub(test_user, plan="starter")
        db.add(sub)
        await db.flush()

        # Payment fails
        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "invoice.payment_failed",
                {"subscription": sub.stripe_subscription_id},
            )
            await billing_service.handle_stripe_webhook(db, b"p", "s")

        await db.refresh(sub)
        assert sub.status == "past_due"
        # User still has starter access (past_due is in active set)
        assert await billing_service.get_plan_name(db, test_user) == "starter"

        # Payment succeeds after card update
        with patch("app.services.billing_service.stripe") as mock_stripe:
            mock_stripe.Webhook.construct_event.return_value = _webhook_event(
                "invoice.payment_succeeded",
                {"subscription": sub.stripe_subscription_id},
            )
            await billing_service.handle_stripe_webhook(db, b"p", "s")

        await db.refresh(sub)
        assert sub.status == "active"


# ── Downgrade Edge Cases ────────────────────────────────────────────


@pytest.mark.asyncio
class TestDowngradeEdgeCases:
    async def test_downgrade_with_existing_connections_above_new_limit(
        self, db: AsyncSession, test_user: User, test_project: Project, test_provider
    ):
        """User on pro (100 conns) has 50 connections, downgrades to starter (20).
        Existing connections are NOT deleted — but user can't add more."""
        db.add(_make_sub(test_user, plan="pro"))
        # Create 50 connections
        for i in range(50):
            db.add(_make_connection(test_project, test_user, test_provider.id))
        await db.flush()

        # Currently on pro, 50 < 100 so check passes
        await billing_service.check_connection_limit(db, test_user)

        # Simulate downgrade to starter via webhook
        result = await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )
        sub = result.scalar_one()
        sub.plan_name = "starter"
        await db.flush()

        # Now on starter (limit 20), with 50 connections — new connections should be blocked
        with pytest.raises(ForbiddenError, match="Connection limit reached"):
            await billing_service.check_connection_limit(db, test_user)

    async def test_downgrade_does_not_affect_retrieval_count(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """After downgrade, existing usage for the period stays but new retrievals are blocked."""
        db.add(_make_sub(test_user, plan="pro"))
        today = date.today()
        period_start = today.replace(day=1)
        # 30000 retrievals used (within pro limit of 500K, but above starter limit of 50K... actually no, 30K < 50K)
        # Let's use 60000 which is above starter (50K) but below pro (500K)
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=period_start,
            token_retrievals=60000,
            connections_count=0,
        ))
        await db.flush()

        # On pro, 60K < 500K
        await billing_service.check_retrieval_limit(db, test_user)

        # Downgrade to starter
        result = await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )
        sub = result.scalar_one()
        sub.plan_name = "starter"
        await db.flush()

        # Now on starter, 60K > 50K limit
        with pytest.raises(ForbiddenError, match="Token retrieval limit reached"):
            await billing_service.check_retrieval_limit(db, test_user)


# ── Webhook Ordering Edge Cases ─────────────────────────────────────


@pytest.mark.asyncio
class TestWebhookOrdering:
    @patch("app.services.billing_service.stripe")
    async def test_subscription_updated_before_checkout_completed(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """subscription.updated arrives before checkout.session.completed.
        Since no subscription exists yet, the update is a no-op. The checkout
        then creates the subscription."""
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"

        # Step 1: subscription.updated arrives first — no subscription exists → no-op
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "customer.subscription.updated",
            {
                "id": sub_id,
                "status": "active",
                "cancel_at_period_end": False,
                "current_period_start": 1700000000,
                "current_period_end": 1702592000,
            },
        )
        await billing_service.handle_stripe_webhook(db, b"p", "s")

        # No subscription should exist yet
        subs = (await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )).scalars().all()
        assert len(subs) == 0

        # Step 2: checkout.session.completed arrives — creates subscription
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {
                "subscription": sub_id,
                "metadata": {"user_id": str(test_user.id), "plan": "starter"},
            },
        )
        mock_stripe.Subscription.retrieve.return_value = {
            "id": sub_id,
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }
        await billing_service.handle_stripe_webhook(db, b"p", "s")

        subs = (await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )).scalars().all()
        assert len(subs) == 1
        assert subs[0].plan_name == "starter"

    @patch("app.services.billing_service.stripe")
    async def test_payment_failed_before_subscription_exists(
        self, mock_stripe, db: AsyncSession
    ):
        """invoice.payment_failed for a subscription that hasn't been created yet → no-op."""
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "invoice.payment_failed",
            {"subscription": "sub_not_yet_created"},
        )
        result = await billing_service.handle_stripe_webhook(db, b"p", "s")
        assert result == {"received": True}

    @patch("app.services.billing_service.stripe")
    async def test_duplicate_checkout_completed_does_not_create_duplicate_sub(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """Two checkout.session.completed events for same subscription → only one record."""
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
        event1_id = f"evt_{uuid.uuid4().hex[:16]}"
        event2_id = f"evt_{uuid.uuid4().hex[:16]}"

        def make_checkout_event(eid):
            return {
                "id": eid,
                "type": "checkout.session.completed",
                "data": {
                    "object": {
                        "subscription": sub_id,
                        "metadata": {"user_id": str(test_user.id), "plan": "starter"},
                    }
                },
            }

        mock_stripe.Subscription.retrieve.return_value = {
            "id": sub_id,
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }

        # First event
        mock_stripe.Webhook.construct_event.return_value = make_checkout_event(event1_id)
        await billing_service.handle_stripe_webhook(db, b"p", "s")

        # Second event (different event_id but same subscription)
        mock_stripe.Webhook.construct_event.return_value = make_checkout_event(event2_id)
        await billing_service.handle_stripe_webhook(db, b"p", "s")

        # Should still only have one subscription (upsert by stripe_subscription_id)
        subs = (await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )).scalars().all()
        assert len(subs) == 1


# ── Deleted User / Missing Data ─────────────────────────────────────


@pytest.mark.asyncio
class TestMissingData:
    @patch("app.services.billing_service.stripe")
    async def test_checkout_for_deleted_user_id(
        self, mock_stripe, db: AsyncSession
    ):
        """checkout.session.completed with a user_id that doesn't exist in DB.
        Should fail gracefully (IntegrityError on FK) but not crash silently."""
        fake_user_id = str(uuid.uuid4())
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {
                "subscription": sub_id,
                "metadata": {"user_id": fake_user_id, "plan": "starter"},
            },
        )
        mock_stripe.Subscription.retrieve.return_value = {
            "id": sub_id,
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }

        # This should raise an IntegrityError (FK violation) since user doesn't exist
        with pytest.raises(Exception):
            await billing_service.handle_stripe_webhook(db, b"p", "s")

    @patch("app.services.billing_service.stripe")
    async def test_checkout_missing_metadata(self, mock_stripe, db: AsyncSession):
        """checkout.session.completed with no metadata at all."""
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {"subscription": "sub_x"},
        )
        mock_stripe.Subscription.retrieve.return_value = {
            "id": "sub_x",
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }

        # No user_id in metadata → should be ignored
        result = await billing_service.handle_stripe_webhook(db, b"p", "s")
        assert result == {"received": True}


# ── Stripe API Failures ─────────────────────────────────────────────


@pytest.mark.asyncio
class TestStripeAPIFailures:
    @patch("app.services.billing_service._run_stripe")
    async def test_checkout_creation_stripe_api_error(
        self, mock_run_stripe, db: AsyncSession, test_user: User
    ):
        """Stripe API down during checkout creation should propagate the error."""
        import stripe as stripe_lib
        mock_run_stripe.side_effect = stripe_lib.APIConnectionError("Stripe is down")

        test_user.stripe_customer_id = "cus_existing"
        await db.flush()

        with patch.dict(billing_service.PLAN_PRICES, {"starter": "price_starter_test"}):
            with pytest.raises(stripe_lib.APIConnectionError):
                await billing_service.create_checkout_session(db, test_user, "starter")

    @patch("app.services.billing_service._run_stripe")
    async def test_portal_creation_stripe_api_error(
        self, mock_run_stripe, db: AsyncSession, test_user: User
    ):
        """Stripe API down during portal creation should propagate the error."""
        import stripe as stripe_lib
        mock_run_stripe.side_effect = stripe_lib.APIConnectionError("Stripe is down")

        test_user.stripe_customer_id = "cus_existing"
        await db.flush()

        with pytest.raises(stripe_lib.APIConnectionError):
            await billing_service.create_portal_session(db, test_user)

    @patch("app.services.billing_service.stripe")
    async def test_checkout_webhook_stripe_retrieve_failure(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """Stripe.Subscription.retrieve fails during checkout webhook processing."""
        import stripe as stripe_lib

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {
                "subscription": "sub_x",
                "metadata": {"user_id": str(test_user.id), "plan": "pro"},
            },
        )
        mock_stripe.Subscription.retrieve.side_effect = stripe_lib.APIConnectionError("Stripe down")

        with pytest.raises(stripe_lib.APIConnectionError):
            await billing_service.handle_stripe_webhook(db, b"p", "s")


# ── Multiple Subscriptions ──────────────────────────────────────────


@pytest.mark.asyncio
class TestMultipleSubscriptions:
    async def test_multiple_active_subscriptions_returns_latest(
        self, db: AsyncSession, test_user: User
    ):
        """If user has multiple active subscriptions, the one with latest period_end wins."""
        db.add(_make_sub(
            test_user, plan="starter",
            period_end=datetime.now(timezone.utc) + timedelta(days=10),
        ))
        db.add(_make_sub(
            test_user, plan="pro",
            period_end=datetime.now(timezone.utc) + timedelta(days=30),
        ))
        await db.flush()

        # Pro has later period_end, so it should be returned
        plan = await billing_service.get_plan_name(db, test_user)
        assert plan == "pro"

    async def test_only_active_statuses_considered(
        self, db: AsyncSession, test_user: User
    ):
        """Canceled + active subscription — only active one counts."""
        db.add(_make_sub(test_user, plan="pro", status="canceled"))
        db.add(_make_sub(test_user, plan="starter", status="active"))
        await db.flush()

        plan = await billing_service.get_plan_name(db, test_user)
        assert plan == "starter"


# ── Usage Period Boundary ───────────────────────────────────────────


@pytest.mark.asyncio
class TestUsagePeriodBoundary:
    async def test_usage_resets_at_month_boundary(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Usage from previous month should not count toward current month limit."""
        today = date.today()
        current_period = today.replace(day=1)
        prev_period = (current_period - timedelta(days=1)).replace(day=1)

        # Heavy usage last month
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=prev_period,
            token_retrievals=999,
            connections_count=5,
        ))
        # Light usage this month
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=current_period,
            token_retrievals=10,
            connections_count=1,
        ))
        await db.flush()

        usage = await billing_service.get_usage(db, test_user)
        assert usage["token_retrievals"] == 10
        assert usage["connections_count"] == 1

    async def test_track_retrieval_on_first_day_of_month(
        self, db: AsyncSession, test_project: Project
    ):
        """Tracking on the 1st of the month should create a record with correct period_start."""
        await billing_service.track_token_retrieval(db, test_project.id)

        result = await db.execute(
            select(UsageRecord).where(UsageRecord.project_id == test_project.id)
        )
        record = result.scalar_one()
        assert record.period_start == date.today().replace(day=1)
        assert record.token_retrievals == 1


# ── Checkout Session Edge Cases ─────────────────────────────────────


@pytest.mark.asyncio
class TestCheckoutEdgeCases:
    async def test_checkout_unknown_plan_raises_bad_request(
        self, db: AsyncSession, test_user: User
    ):
        """Unknown plan name should raise BadRequestError."""
        with pytest.raises(BadRequestError, match="Unknown plan"):
            await billing_service.create_checkout_session(db, test_user, "nonexistent_plan_xyz")

    async def test_checkout_enterprise_plan_not_in_prices(
        self, db: AsyncSession, test_user: User
    ):
        """Enterprise is not in PLAN_PRICES — should raise BadRequestError."""
        # Enterprise has infinite limits but no Stripe price
        assert "enterprise" not in billing_service.PLAN_PRICES
        with pytest.raises(BadRequestError, match="Unknown plan"):
            await billing_service.create_checkout_session(db, test_user, "enterprise")

    @patch("app.services.billing_service.stripe")
    async def test_new_user_gets_stripe_customer_on_first_checkout(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """User with no stripe_customer_id gets one created during checkout."""
        assert test_user.stripe_customer_id is None

        mock_stripe.Customer.create.return_value = MagicMock(id="cus_brand_new")
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_stripe.checkout.Session.create.return_value = mock_session

        with patch.dict(billing_service.PLAN_PRICES, {"starter": "price_starter_test"}):
            result = await billing_service.create_checkout_session(db, test_user, "starter")

        assert test_user.stripe_customer_id == "cus_brand_new"
        assert result["checkout_url"] == "https://checkout.stripe.com/test"


# ── Billing API Endpoint Edge Cases ─────────────────────────────────


@pytest.mark.asyncio
class TestBillingAPIEdgeCases:
    async def test_billing_config_returns_all_plans(self):
        """Config endpoint should return all defined plans."""
        assert "free" in billing_service.PLAN_LIMITS
        assert "starter" in billing_service.PLAN_LIMITS
        assert "pro" in billing_service.PLAN_LIMITS
        assert "enterprise" in billing_service.PLAN_LIMITS

    async def test_price_to_plan_reverse_lookup(self):
        """PRICE_TO_PLAN maps price_ids back to plan names for upgrade detection."""
        # Only non-empty price_ids should be in the lookup
        for plan_name, price_id in billing_service.PLAN_PRICES.items():
            if price_id:
                assert billing_service.PRICE_TO_PLAN[price_id] == plan_name

    async def test_subscription_response_includes_period_end(
        self, db: AsyncSession, test_user: User
    ):
        """Active subscription response should include current_period_end."""
        period_end = datetime(2026, 5, 1, tzinfo=timezone.utc)
        db.add(_make_sub(test_user, plan="pro", period_end=period_end))
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["current_period_end"] == period_end.isoformat()
