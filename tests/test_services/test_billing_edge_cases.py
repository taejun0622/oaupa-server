"""Comprehensive billing edge case tests.

Covers: plan limits, usage tracking, webhook idempotency, subscription state
transitions, race conditions, and period boundary edge cases.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
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
        stripe_subscription_id=f"sub_{uuid.uuid4().hex[:16]}",
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


# ── Connection Limit Tests ──────────────────────────────────────────


@pytest.mark.asyncio
class TestConnectionLimits:
    async def test_free_user_at_limit_is_blocked(
        self, db: AsyncSession, test_user: User, test_project: Project, test_provider
    ):
        """Free plan allows 3 connections. At exactly 3, next should be blocked."""
        for i in range(3):
            db.add(_make_connection(test_project, test_user, test_provider.id))
        await db.flush()

        with pytest.raises(ForbiddenError, match="Connection limit reached"):
            await billing_service.check_connection_limit(db, test_user)

    async def test_free_user_below_limit_is_allowed(
        self, db: AsyncSession, test_user: User, test_project: Project, test_provider
    ):
        """Free plan allows 3 — 2 existing connections should pass."""
        for i in range(2):
            db.add(_make_connection(test_project, test_user, test_provider.id))
        await db.flush()

        # Should not raise
        await billing_service.check_connection_limit(db, test_user)

    async def test_revoked_connections_not_counted(
        self, db: AsyncSession, test_user: User, test_project: Project, test_provider
    ):
        """Revoked connections should not count toward the limit."""
        for i in range(3):
            db.add(_make_connection(test_project, test_user, test_provider.id, status="revoked"))
        await db.flush()

        # All 3 are revoked, so user should be at 0 active
        await billing_service.check_connection_limit(db, test_user)

    async def test_enterprise_user_bypasses_limit(
        self, db: AsyncSession, test_user: User, test_project: Project, test_provider
    ):
        """Enterprise plan has infinite connections."""
        db.add(_make_sub(test_user, plan="enterprise"))
        for i in range(200):
            db.add(_make_connection(test_project, test_user, test_provider.id))
        await db.flush()

        # Should not raise despite 200 connections
        await billing_service.check_connection_limit(db, test_user)

    async def test_starter_plan_limit(
        self, db: AsyncSession, test_user: User, test_project: Project, test_provider
    ):
        """Starter plan allows 20 connections."""
        db.add(_make_sub(test_user, plan="starter"))
        for i in range(20):
            db.add(_make_connection(test_project, test_user, test_provider.id))
        await db.flush()

        with pytest.raises(ForbiddenError, match="Connection limit reached"):
            await billing_service.check_connection_limit(db, test_user)

    async def test_connections_across_multiple_projects(
        self, db: AsyncSession, test_user: User, test_provider
    ):
        """Limits count connections across ALL projects for a user."""
        proj1 = Project(user_id=test_user.id, name="P1", slug=f"p1-{uuid.uuid4().hex[:8]}")
        proj2 = Project(user_id=test_user.id, name="P2", slug=f"p2-{uuid.uuid4().hex[:8]}")
        db.add_all([proj1, proj2])
        await db.flush()

        # 2 connections in proj1, 1 in proj2 = 3 total = at free limit
        db.add(_make_connection(proj1, test_user, test_provider.id))
        db.add(_make_connection(proj1, test_user, test_provider.id))
        db.add(_make_connection(proj2, test_user, test_provider.id))
        await db.flush()

        with pytest.raises(ForbiddenError, match="Connection limit reached"):
            await billing_service.check_connection_limit(db, test_user)


# ── Retrieval Limit Tests ───────────────────────────────────────────


@pytest.mark.asyncio
class TestRetrievalLimits:
    async def test_free_user_at_retrieval_limit(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Free plan allows 1000 token retrievals per month."""
        today = date.today()
        period_start = today.replace(day=1)
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=period_start,
            token_retrievals=1000,
            connections_count=0,
        ))
        await db.flush()

        with pytest.raises(ForbiddenError, match="Token retrieval limit reached"):
            await billing_service.check_retrieval_limit(db, test_user)

    async def test_free_user_below_retrieval_limit(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """999 retrievals on free plan should be allowed."""
        today = date.today()
        period_start = today.replace(day=1)
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=period_start,
            token_retrievals=999,
            connections_count=0,
        ))
        await db.flush()

        # Should not raise
        await billing_service.check_retrieval_limit(db, test_user)

    async def test_enterprise_user_bypasses_retrieval_limit(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Enterprise plan has infinite retrievals."""
        db.add(_make_sub(test_user, plan="enterprise"))
        today = date.today()
        period_start = today.replace(day=1)
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=period_start,
            token_retrievals=1_000_000,
            connections_count=0,
        ))
        await db.flush()

        await billing_service.check_retrieval_limit(db, test_user)

    async def test_previous_month_usage_not_counted(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        """Usage from previous months should not affect current period limit."""
        today = date.today()
        last_month = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        # Last month: 999 retrievals (at limit - 1)
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=last_month,
            token_retrievals=999,
            connections_count=0,
        ))
        await db.flush()

        # Current month has zero usage, so should not raise
        await billing_service.check_retrieval_limit(db, test_user)

    async def test_usage_summed_across_projects(
        self, db: AsyncSession, test_user: User
    ):
        """Retrieval limits sum usage across all user's projects."""
        proj1 = Project(user_id=test_user.id, name="P1", slug=f"p1-{uuid.uuid4().hex[:8]}")
        proj2 = Project(user_id=test_user.id, name="P2", slug=f"p2-{uuid.uuid4().hex[:8]}")
        db.add_all([proj1, proj2])
        await db.flush()

        today = date.today()
        period_start = today.replace(day=1)
        # 600 in proj1 + 400 in proj2 = 1000 = at limit
        db.add(UsageRecord(project_id=proj1.id, period_start=period_start, token_retrievals=600, connections_count=0))
        db.add(UsageRecord(project_id=proj2.id, period_start=period_start, token_retrievals=400, connections_count=0))
        await db.flush()

        with pytest.raises(ForbiddenError, match="Token retrieval limit reached"):
            await billing_service.check_retrieval_limit(db, test_user)


# ── Usage Tracking Tests ────────────────────────────────────────────


@pytest.mark.asyncio
class TestUsageTracking:
    async def test_track_creates_new_record(
        self, db: AsyncSession, test_project: Project
    ):
        await billing_service.track_token_retrieval(db, test_project.id)

        result = await db.execute(
            select(UsageRecord).where(UsageRecord.project_id == test_project.id)
        )
        record = result.scalar_one()
        assert record.token_retrievals == 1
        assert record.period_start == date.today().replace(day=1)

    async def test_track_increments_existing_record(
        self, db: AsyncSession, test_project: Project
    ):
        today = date.today()
        period_start = today.replace(day=1)
        db.add(UsageRecord(
            project_id=test_project.id,
            period_start=period_start,
            token_retrievals=42,
            connections_count=0,
        ))
        await db.flush()

        await billing_service.track_token_retrieval(db, test_project.id)

        result = await db.execute(
            select(UsageRecord).where(UsageRecord.project_id == test_project.id)
        )
        record = result.scalar_one()
        assert record.token_retrievals == 43

    async def test_multiple_tracks_increment_correctly(
        self, db: AsyncSession, test_project: Project
    ):
        for _ in range(5):
            await billing_service.track_token_retrieval(db, test_project.id)

        result = await db.execute(
            select(UsageRecord).where(UsageRecord.project_id == test_project.id)
        )
        record = result.scalar_one()
        assert record.token_retrievals == 5


# ── Get Usage Tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetUsage:
    async def test_zero_usage_for_new_user(self, db: AsyncSession, test_user: User):
        result = await billing_service.get_usage(db, test_user)
        assert result["token_retrievals"] == 0
        assert result["connections_count"] == 0

    async def test_returns_current_month_only(
        self, db: AsyncSession, test_user: User, test_project: Project
    ):
        today = date.today()
        current_period = today.replace(day=1)
        last_month = (current_period - timedelta(days=1)).replace(day=1)

        db.add(UsageRecord(
            project_id=test_project.id, period_start=last_month,
            token_retrievals=999, connections_count=10,
        ))
        db.add(UsageRecord(
            project_id=test_project.id, period_start=current_period,
            token_retrievals=42, connections_count=3,
        ))
        await db.flush()

        result = await billing_service.get_usage(db, test_user)
        assert result["token_retrievals"] == 42
        assert result["connections_count"] == 3


# ── Subscription State Tests ────────────────────────────────────────


@pytest.mark.asyncio
class TestSubscriptionState:
    async def test_no_subscription_returns_free(self, db: AsyncSession, test_user: User):
        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "free"
        assert result["status"] == "active"
        assert result["limits"]["connections"] == 3

    async def test_past_due_subscription_is_still_active(self, db: AsyncSession, test_user: User):
        """past_due is returned by _get_active_subscription (included in the IN clause)."""
        db.add(_make_sub(test_user, plan="pro", status="past_due"))
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "pro"
        assert result["status"] == "past_due"

    async def test_trialing_subscription_is_active(self, db: AsyncSession, test_user: User):
        db.add(_make_sub(test_user, plan="starter", status="trialing"))
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "starter"
        assert result["status"] == "trialing"

    async def test_canceled_subscription_returns_free(self, db: AsyncSession, test_user: User):
        """Canceled subscriptions are not in the active set, so user falls back to free."""
        db.add(_make_sub(test_user, plan="pro", status="canceled"))
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "free"

    async def test_cancel_at_period_end_still_active(self, db: AsyncSession, test_user: User):
        db.add(_make_sub(test_user, plan="pro", cancel_at_period_end=True))
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "pro"
        assert result["cancel_at_period_end"] is True

    async def test_unknown_plan_falls_back_to_free_limits(self, db: AsyncSession, test_user: User):
        """If plan_name is unknown, PLAN_LIMITS.get() falls back to free limits."""
        db.add(_make_sub(test_user, plan="nonexistent_plan"))
        await db.flush()

        result = await billing_service.get_subscription(db, test_user)
        assert result["plan"] == "nonexistent_plan"
        assert result["limits"]["connections"] == 3  # free fallback


# ── Webhook Idempotency Tests ───────────────────────────────────────


@pytest.mark.asyncio
class TestWebhookIdempotency:
    @patch("app.services.billing_service.stripe")
    async def test_duplicate_event_is_skipped(self, mock_stripe, db: AsyncSession, test_user: User):
        """Same event_id processed twice should only apply once."""
        event_id = f"evt_{uuid.uuid4().hex[:16]}"

        # Pre-record the event
        db.add(StripeEvent(event_id=event_id, event_type="checkout.session.completed"))
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {"subscription": "sub_x", "metadata": {"user_id": str(test_user.id), "plan": "pro"}},
            event_id=event_id,
        )

        result = await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        assert result == {"received": True}

        # Should NOT have created a subscription
        subs = (await db.execute(select(Subscription).where(Subscription.user_id == test_user.id))).scalars().all()
        assert len(subs) == 0

    @patch("app.services.billing_service.stripe")
    async def test_new_event_is_recorded(self, mock_stripe, db: AsyncSession, test_user: User):
        """After processing, the event_id should be stored in stripe_events."""
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "invoice.payment_failed",
            {"subscription": "sub_nonexistent"},
            event_id=event_id,
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")

        result = await db.execute(
            select(StripeEvent).where(StripeEvent.event_id == event_id)
        )
        assert result.scalar_one_or_none() is not None


# ── Webhook Event Handling Tests ────────────────────────────────────


@pytest.mark.asyncio
class TestWebhookHandlers:
    @patch("app.services.billing_service.stripe")
    async def test_checkout_completed_creates_subscription(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
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

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")

        result = await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )
        sub = result.scalar_one()
        assert sub.plan_name == "starter"
        assert sub.status == "active"

    @patch("app.services.billing_service.stripe")
    async def test_checkout_without_subscription_id_is_noop(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """checkout.session.completed without subscription field is ignored."""
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {"metadata": {"user_id": str(test_user.id), "plan": "pro"}},
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")

        subs = (await db.execute(select(Subscription).where(Subscription.user_id == test_user.id))).scalars().all()
        assert len(subs) == 0

    @patch("app.services.billing_service.stripe")
    async def test_checkout_without_user_id_is_noop(
        self, mock_stripe, db: AsyncSession
    ):
        """checkout.session.completed without user_id in metadata is ignored."""
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {"subscription": "sub_orphan", "metadata": {}},
        )
        mock_stripe.Subscription.retrieve.return_value = {
            "id": "sub_orphan",
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_starter"}}]},
        }

        result = await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        assert result == {"received": True}

    @patch("app.services.billing_service.stripe")
    async def test_subscription_update_changes_status(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        sub = _make_sub(test_user, plan="pro")
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "customer.subscription.updated",
            {
                "id": sub.stripe_subscription_id,
                "status": "past_due",
                "cancel_at_period_end": True,
                "current_period_start": 1700000000,
                "current_period_end": 1702592000,
            },
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        await db.refresh(sub)
        assert sub.status == "past_due"
        assert sub.cancel_at_period_end is True

    @patch("app.services.billing_service.stripe")
    async def test_subscription_update_detects_plan_change(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """When a user upgrades via Stripe portal, the price_id changes."""
        sub = _make_sub(test_user, plan="starter")
        sub.stripe_price_id = "price_starter"
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "customer.subscription.updated",
            {
                "id": sub.stripe_subscription_id,
                "status": "active",
                "cancel_at_period_end": False,
                "items": {"data": [{"price": {"id": "price_pro"}}]},
            },
        )

        # Set up PRICE_TO_PLAN to map the test price
        with patch.dict(billing_service.PRICE_TO_PLAN, {"price_pro": "pro"}):
            await billing_service.handle_stripe_webhook(db, b"payload", "sig")

        await db.refresh(sub)
        assert sub.plan_name == "pro"
        assert sub.stripe_price_id == "price_pro"

    @patch("app.services.billing_service.stripe")
    async def test_subscription_deleted_marks_status(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        sub = _make_sub(test_user, plan="pro")
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "customer.subscription.deleted",
            {
                "id": sub.stripe_subscription_id,
                "status": "canceled",
                "cancel_at_period_end": False,
            },
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        await db.refresh(sub)
        assert sub.status == "canceled"

    @patch("app.services.billing_service.stripe")
    async def test_payment_failed_sets_past_due(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        sub = _make_sub(test_user, plan="starter")
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "invoice.payment_failed",
            {"subscription": sub.stripe_subscription_id},
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        await db.refresh(sub)
        assert sub.status == "past_due"

    @patch("app.services.billing_service.stripe")
    async def test_payment_succeeded_recovers_past_due(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        sub = _make_sub(test_user, plan="starter", status="past_due")
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "invoice.payment_succeeded",
            {"subscription": sub.stripe_subscription_id},
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        await db.refresh(sub)
        assert sub.status == "active"

    @patch("app.services.billing_service.stripe")
    async def test_payment_succeeded_does_not_change_active_subscription(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """payment_succeeded only changes status if it was past_due."""
        sub = _make_sub(test_user, plan="starter", status="active")
        db.add(sub)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "invoice.payment_succeeded",
            {"subscription": sub.stripe_subscription_id},
        )

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        await db.refresh(sub)
        assert sub.status == "active"

    @patch("app.services.billing_service.stripe")
    async def test_payment_failed_unknown_subscription_is_noop(
        self, mock_stripe, db: AsyncSession
    ):
        """payment_failed for a subscription_id we don't have is silently ignored."""
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "invoice.payment_failed",
            {"subscription": "sub_unknown_999"},
        )

        result = await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        assert result == {"received": True}

    @patch("app.services.billing_service.stripe")
    async def test_unhandled_event_type_is_accepted(self, mock_stripe, db: AsyncSession):
        """Unknown event types should be accepted but not processed."""
        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "some.future.event",
            {"foo": "bar"},
        )

        result = await billing_service.handle_stripe_webhook(db, b"payload", "sig")
        assert result == {"received": True}


# ── Checkout & Portal Tests ─────────────────────────────────────────


@pytest.mark.asyncio
class TestCheckoutAndPortal:
    async def test_unknown_plan_raises_bad_request(self, db: AsyncSession, test_user: User):
        with pytest.raises(BadRequestError, match="Unknown plan"):
            await billing_service.create_checkout_session(db, test_user, "nonexistent_plan")

    @patch("app.services.billing_service.stripe")
    async def test_checkout_creates_customer_if_needed(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """Checkout for user without stripe_customer_id creates a customer first."""
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_new")
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/test"
        mock_stripe.checkout.Session.create.return_value = mock_session

        with patch.dict(billing_service.PLAN_PRICES, {"starter": "price_starter_test"}):
            result = await billing_service.create_checkout_session(db, test_user, "starter")

        assert result["checkout_url"] == "https://checkout.stripe.com/test"
        assert test_user.stripe_customer_id == "cus_new"

    @patch("app.services.billing_service.stripe")
    async def test_portal_reuses_existing_customer(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        test_user.stripe_customer_id = "cus_existing"
        await db.flush()

        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/portal"
        mock_stripe.billing_portal.Session.create.return_value = mock_session

        result = await billing_service.create_portal_session(db, test_user)
        assert result["portal_url"] == "https://billing.stripe.com/portal"


# ── Plan Config Tests ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestPlanConfig:
    async def test_plan_limits_are_complete(self):
        """Ensure all expected plans are defined."""
        assert "free" in billing_service.PLAN_LIMITS
        assert "starter" in billing_service.PLAN_LIMITS
        assert "pro" in billing_service.PLAN_LIMITS
        assert "enterprise" in billing_service.PLAN_LIMITS

    async def test_enterprise_has_infinite_limits(self):
        limits = billing_service.PLAN_LIMITS["enterprise"]
        assert limits["connections"] == float("inf")
        assert limits["token_retrievals"] == float("inf")

    async def test_free_plan_has_lowest_limits(self):
        free = billing_service.PLAN_LIMITS["free"]
        starter = billing_service.PLAN_LIMITS["starter"]
        pro = billing_service.PLAN_LIMITS["pro"]
        assert free["connections"] < starter["connections"] < pro["connections"]
        assert free["token_retrievals"] < starter["token_retrievals"] < pro["token_retrievals"]

    async def test_infinity_converted_to_negative_one_in_schema(self):
        """PlanLimits schema converts float('inf') to -1 for JSON serialization."""
        from app.schemas.billing import PlanLimits
        limits = PlanLimits(**billing_service.PLAN_LIMITS["enterprise"])
        assert limits.connections == -1
        assert limits.token_retrievals == -1


# ── Checkout Upsert (Existing Subscription) ────────────────────────


@pytest.mark.asyncio
class TestCheckoutUpsert:
    @patch("app.services.billing_service.stripe")
    async def test_checkout_completed_upserts_existing_subscription(
        self, mock_stripe, db: AsyncSession, test_user: User
    ):
        """If subscription already exists (e.g., from a prior webhook), it should be updated, not duplicated."""
        sub_id = f"sub_{uuid.uuid4().hex[:16]}"
        existing = Subscription(
            user_id=test_user.id,
            stripe_subscription_id=sub_id,
            stripe_price_id="price_old",
            plan_name="starter",
            status="active",
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
        db.add(existing)
        await db.flush()

        mock_stripe.Webhook.construct_event.return_value = _webhook_event(
            "checkout.session.completed",
            {
                "subscription": sub_id,
                "metadata": {"user_id": str(test_user.id), "plan": "pro"},
            },
        )
        mock_stripe.Subscription.retrieve.return_value = {
            "id": sub_id,
            "status": "active",
            "current_period_start": 1700000000,
            "current_period_end": 1702592000,
            "items": {"data": [{"price": {"id": "price_pro"}}]},
        }

        await billing_service.handle_stripe_webhook(db, b"payload", "sig")

        subs = (await db.execute(
            select(Subscription).where(Subscription.user_id == test_user.id)
        )).scalars().all()
        assert len(subs) == 1
        assert subs[0].plan_name == "pro"


# ── Webhook Signature Tests ─────────────────────────────────────────


@pytest.mark.asyncio
class TestWebhookSignature:
    async def test_invalid_signature_raises(self, db: AsyncSession):
        with pytest.raises(BadRequestError, match="Invalid webhook signature"):
            await billing_service.handle_stripe_webhook(db, b"bad-payload", "bad-sig")

    async def test_empty_payload_raises(self, db: AsyncSession):
        with pytest.raises(BadRequestError, match="Invalid webhook signature"):
            await billing_service.handle_stripe_webhook(db, b"", "")
