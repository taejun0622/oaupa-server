from math import isinf

from pydantic import BaseModel, model_validator


class PlanLimits(BaseModel):
    connections: int
    token_retrievals: int

    @model_validator(mode="before")
    @classmethod
    def convert_infinity(cls, data):
        if isinstance(data, dict):
            for key in ("connections", "token_retrievals"):
                val = data.get(key)
                if isinstance(val, float) and isinf(val):
                    data[key] = -1
        return data


class SubscriptionResponse(BaseModel):
    plan: str
    status: str
    current_period_end: str | None = None
    cancel_at_period_end: bool = False
    limits: PlanLimits


class CheckoutRequest(BaseModel):
    plan: str


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalResponse(BaseModel):
    portal_url: str


class UsageResponse(BaseModel):
    token_retrievals: int
    connections_count: int
    limits: PlanLimits | None = None
    warnings: list[str] = []


class InvoiceResponse(BaseModel):
    id: str
    amount_due: int
    amount_paid: int
    currency: str
    status: str | None
    period_start: str | None
    period_end: str | None
    invoice_url: str | None
    created: str | None


class StripeWebhookResponse(BaseModel):
    received: bool


class BillingConfigResponse(BaseModel):
    stripe_publishable_key: str
    plans: dict[str, PlanLimits]
