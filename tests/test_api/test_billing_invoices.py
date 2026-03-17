"""Tests for GET /api/v1/billing/invoices endpoint."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient

from tests.conftest import auth_headers


# ── Helpers ─────────────────────────────────────────────────────────────────


def _stripe_invoice(
    inv_id: str = "in_test001",
    amount_due: int = 2900,
    amount_paid: int = 2900,
    currency: str = "usd",
    status: str = "paid",
    period_start: int = 1700000000,
    period_end: int = 1702592000,
    hosted_invoice_url: str = "https://invoice.stripe.com/test",
    created: int = 1700000001,
) -> dict:
    """Return a minimal Stripe invoice dict."""
    return {
        "id": inv_id,
        "amount_due": amount_due,
        "amount_paid": amount_paid,
        "currency": currency,
        "status": status,
        "period_start": period_start,
        "period_end": period_end,
        "hosted_invoice_url": hosted_invoice_url,
        "created": created,
    }


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestGetInvoices:
    async def test_unauthenticated_returns_401_or_422(self, client: AsyncClient):
        """Request without auth token is rejected."""
        resp = await client.get("/api/v1/billing/invoices")
        assert resp.status_code in (401, 422)

    async def test_authenticated_no_stripe_customer_returns_empty_list(
        self, client: AsyncClient
    ):
        """User with no Stripe customer ID gets an empty list, not an error."""
        headers = await auth_headers(client)
        resp = await client.get("/api/v1/billing/invoices", headers=headers)
        assert resp.status_code == 200
        assert resp.json() == []

    @patch("app.services.billing_service.stripe")
    async def test_authenticated_with_invoices_returns_list(
        self, mock_stripe, client: AsyncClient
    ):
        """User with a Stripe customer receives their invoice list."""
        mock_stripe.Customer.create.return_value = MagicMock(id="cus_test_inv")
        inv = _stripe_invoice()
        mock_stripe.Invoice.list.return_value = {"data": [inv]}

        headers = await auth_headers(client)

        # Give the user a stripe_customer_id via the ensure helper so the
        # service actually calls stripe.Invoice.list.
        from sqlalchemy import select
        from app.models.user import User as UserModel
        from app.db.session import get_db

        # Use the override db from the client fixture to set stripe_customer_id.
        # We do this by calling a checkout that will create the customer, but
        # it's simpler to call the internal _ensure helper via a separate step.
        # Instead, patch get_invoices to simulate a user with a customer ID.
        with patch(
            "app.services.billing_service.get_invoices",
            return_value=[
                {
                    "id": inv["id"],
                    "amount_due": inv["amount_due"],
                    "amount_paid": inv["amount_paid"],
                    "currency": inv["currency"],
                    "status": inv["status"],
                    "period_start": "2023-11-15T00:00:00+00:00",
                    "period_end": "2023-12-15T00:00:00+00:00",
                    "invoice_url": inv["hosted_invoice_url"],
                    "created": "2023-11-15T00:00:01+00:00",
                }
            ],
        ):
            resp = await client.get("/api/v1/billing/invoices", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["id"] == "in_test001"

    @patch("app.services.billing_service.stripe")
    async def test_invoice_response_schema(self, mock_stripe, client: AsyncClient):
        """Each invoice object contains all required schema fields."""
        inv = _stripe_invoice(inv_id="in_schema_check", amount_due=4900, amount_paid=0, status="open")
        mock_stripe.Invoice.list.return_value = {"data": [inv]}

        headers = await auth_headers(client)

        with patch(
            "app.services.billing_service.get_invoices",
            return_value=[
                {
                    "id": "in_schema_check",
                    "amount_due": 4900,
                    "amount_paid": 0,
                    "currency": "usd",
                    "status": "open",
                    "period_start": "2023-11-15T00:00:00+00:00",
                    "period_end": "2023-12-15T00:00:00+00:00",
                    "invoice_url": "https://invoice.stripe.com/test",
                    "created": "2023-11-15T00:00:01+00:00",
                }
            ],
        ):
            resp = await client.get("/api/v1/billing/invoices", headers=headers)

        assert resp.status_code == 200
        item = resp.json()[0]
        required_keys = {
            "id",
            "amount_due",
            "amount_paid",
            "currency",
            "status",
            "period_start",
            "period_end",
            "invoice_url",
            "created",
        }
        assert required_keys.issubset(set(item.keys()))
        assert item["amount_due"] == 4900
        assert item["amount_paid"] == 0
        assert item["currency"] == "usd"
        assert item["status"] == "open"

    @patch("app.services.billing_service.stripe")
    async def test_multiple_invoices_returned(self, mock_stripe, client: AsyncClient):
        """Multiple invoices are all returned."""
        invoices = [
            {
                "id": f"in_multi_{i}",
                "amount_due": 2900 * (i + 1),
                "amount_paid": 2900 * (i + 1),
                "currency": "usd",
                "status": "paid",
                "period_start": "2023-11-15T00:00:00+00:00",
                "period_end": "2023-12-15T00:00:00+00:00",
                "invoice_url": None,
                "created": "2023-11-15T00:00:01+00:00",
            }
            for i in range(3)
        ]

        headers = await auth_headers(client)

        with patch("app.services.billing_service.get_invoices", return_value=invoices):
            resp = await client.get("/api/v1/billing/invoices", headers=headers)

        assert resp.status_code == 200
        assert len(resp.json()) == 3

    @patch("app.services.billing_service.stripe")
    async def test_invoice_with_null_optional_fields(self, mock_stripe, client: AsyncClient):
        """Invoices with None optional fields are serialised without error."""
        headers = await auth_headers(client)

        with patch(
            "app.services.billing_service.get_invoices",
            return_value=[
                {
                    "id": "in_nulls",
                    "amount_due": 0,
                    "amount_paid": 0,
                    "currency": "usd",
                    "status": None,
                    "period_start": None,
                    "period_end": None,
                    "invoice_url": None,
                    "created": None,
                }
            ],
        ):
            resp = await client.get("/api/v1/billing/invoices", headers=headers)

        assert resp.status_code == 200
        item = resp.json()[0]
        assert item["status"] is None
        assert item["invoice_url"] is None
