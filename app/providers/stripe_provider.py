import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url, exchange_code_standard, refresh_token_standard


class StripeOAuthProvider(OAuthProviderBase):
    provider_id = "stripe"

    def get_authorization_url(
        self, state: str, scopes: list[str], redirect_uri: str, code_challenge: str | None = None
    ) -> str:
        extra = {**self.extra_auth_params, "stripe_landing": "login"}
        return build_authorization_url(
            auth_url=self.auth_url,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes or self.default_scopes,
            extra_params=extra,
        )

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_secret": self.client_secret,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            token_type=body.get("token_type", "bearer"),
            scope=body.get("scope"),
            raw_response=body,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        return await refresh_token_standard(
            self.token_url, self.client_id, self.client_secret, refresh_token
        )

    async def revoke_token(self, token: str) -> bool:
        if not self.revoke_url:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.revoke_url,
                data={"client_id": self.client_id, "stripe_user_id": token},
                auth=httpx.BasicAuth(self.client_secret, ""),
            )
            return resp.status_code == 200

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.stripe.com/v1/account",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=data.get("id", ""),
                email=data.get("email"),
                display_name=data.get("business_profile", {}).get("name"),
            )
