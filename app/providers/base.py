"""Abstract base class for OAuth providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class TokenResponse:
    access_token: str
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_in: int | None = None
    scope: str | None = None
    raw_response: dict | None = None


@dataclass
class AccountInfo:
    account_id: str
    email: str | None = None
    display_name: str | None = None


class OAuthProviderBase(ABC):
    provider_id: str

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        auth_url: str,
        token_url: str,
        revoke_url: str | None = None,
        default_scopes: list[str] | None = None,
        extra_auth_params: dict | None = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.auth_url = auth_url
        self.token_url = token_url
        self.revoke_url = revoke_url
        self.default_scopes = default_scopes or []
        self.extra_auth_params = extra_auth_params or {}

    @abstractmethod
    def get_authorization_url(
        self,
        state: str,
        scopes: list[str],
        redirect_uri: str,
        code_challenge: str | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def exchange_code(
        self,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenResponse:
        ...

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        ...

    async def revoke_token(self, token: str) -> bool:
        return False

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        return None
