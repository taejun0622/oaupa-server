import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url, exchange_code_standard


class TrelloProvider(OAuthProviderBase):
    """Trello uses OAuth 1.0a historically, but Atlassian is migrating to OAuth 2.0 via Power-Ups.
    This implementation uses the newer REST API token approach."""
    provider_id = "trello"

    def get_authorization_url(
        self, state: str, scopes: list[str], redirect_uri: str, code_challenge: str | None = None
    ) -> str:
        extra = {**self.extra_auth_params, "expiration": "never"}
        return build_authorization_url(
            auth_url=self.auth_url,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes or self.default_scopes,
            extra_params=extra,
            scope_separator=",",
        )

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        return await exchange_code_standard(
            self.token_url, self.client_id, self.client_secret, code, redirect_uri, code_verifier
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        raise NotImplementedError("Trello tokens do not expire when set to 'never'")

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.trello.com/1/members/me",
                params={"key": self.client_id, "token": access_token},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=data.get("id", ""),
                email=data.get("email"),
                display_name=data.get("fullName"),
            )
