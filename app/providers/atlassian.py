import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url, exchange_code_standard, refresh_token_standard


class AtlassianProvider(OAuthProviderBase):
    provider_id = "atlassian"

    def get_authorization_url(
        self, state: str, scopes: list[str], redirect_uri: str, code_challenge: str | None = None
    ) -> str:
        extra = {**self.extra_auth_params, "audience": "api.atlassian.com", "prompt": "consent"}
        return build_authorization_url(
            auth_url=self.auth_url,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes or self.default_scopes,
            code_challenge=code_challenge,
            extra_params=extra,
        )

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        return await exchange_code_standard(
            self.token_url, self.client_id, self.client_secret, code, redirect_uri, code_verifier
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        return await refresh_token_standard(
            self.token_url, self.client_id, self.client_secret, refresh_token
        )

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.atlassian.com/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=data.get("account_id", ""),
                email=data.get("email"),
                display_name=data.get("name"),
            )
