import uuid

from pydantic import BaseModel


class OAuthAuthorizeRequest(BaseModel):
    provider_id: str
    project_id: uuid.UUID
    scopes: list[str] | None = None
    redirect_uri: str
    metadata: dict | None = None


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state: str


class ProviderResponse(BaseModel):
    id: str
    display_name: str
    default_scopes: list[str]
    supports_refresh: bool
    is_active: bool
    icon_url: str | None

    model_config = {"from_attributes": True}
