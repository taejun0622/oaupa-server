import uuid
from datetime import datetime

from pydantic import BaseModel


class ConnectionResponse(BaseModel):
    id: uuid.UUID
    provider_id: str
    provider_account_id: str | None
    provider_account_email: str | None
    scopes_granted: list[str]
    status: str
    status_detail: str | None
    last_refreshed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenRetrievalResponse(BaseModel):
    access_token: str
    token_type: str
    expires_at: datetime | None
    connection_id: uuid.UUID
    provider: str
