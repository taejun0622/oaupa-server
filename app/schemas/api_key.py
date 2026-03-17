import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str
    scopes: list[str] = ["tokens:read"]
    expires_at: datetime | None = None


class ApiKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    scopes: list[str]
    last_used_at: datetime | None
    expires_at: datetime | None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyResponse):
    """Returned only at creation time — includes the full key."""
    full_key: str
