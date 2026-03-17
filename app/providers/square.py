import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url


class SquareProvider(OAuthProviderBase):
    provider_id = "square"

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
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            token_type=body.get("token_type", "bearer"),
            expires_at=body.get("expires_at"),
            raw_response=body,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                json={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", refresh_token),
            token_type=body.get("token_type", "bearer"),
            raw_response=body,
        )

    async def revoke_token(self, token: str) -> bool:
        if not self.revoke_url:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.revoke_url,
                json={
                    "client_id": self.client_id,
                    "access_token": token,
                },
            )
            return resp.status_code == 200
