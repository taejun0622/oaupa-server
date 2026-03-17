import uuid
from datetime import datetime

from pydantic import BaseModel


class WebhookResponse(BaseModel):
    id: uuid.UUID
    url: str
    events: list[str]
    is_active: bool
    created_at: datetime | None


class WebhookCreateResponse(BaseModel):
    id: uuid.UUID
    url: str
    secret: str
    events: list[str]
    is_active: bool


class WebhookDeliveryResponse(BaseModel):
    id: uuid.UUID
    event_type: str
    payload: dict | None = None
    response_status: int | None
    response_body: str | None
    attempt_count: int
    delivered_at: datetime | None
    created_at: datetime | None

    model_config = {"from_attributes": True}


class WebhookTestResponse(BaseModel):
    delivery_id: uuid.UUID
    status: str
