import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url


class PayPalProvider(OAuthProviderBase):
    provider_id = "paypal"

    def get_authorization_url(
        self, state: str, scopes: list[str], redirect_uri: str, code_challenge: str | None = None
    ) -> str:
        return build_authorization_url(
            auth_url=self.auth_url,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes or self.default_scopes,
            extra_params=self.extra_auth_params,
        )

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
                auth=httpx.BasicAuth(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            token_type=body.get("token_type", "Bearer"),
            expires_in=body.get("expires_in"),
            raw_response=body,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
                auth=httpx.BasicAuth(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", refresh_token),
            token_type=body.get("token_type", "Bearer"),
            expires_in=body.get("expires_in"),
            raw_response=body,
        )

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.paypal.com/v1/identity/openidconnect/userinfo?schema=openid",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=data.get("user_id", ""),
                email=data.get("email"),
                display_name=data.get("name"),
            )
