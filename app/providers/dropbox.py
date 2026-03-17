import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url


class DropboxProvider(OAuthProviderBase):
    provider_id = "dropbox"

    def get_authorization_url(
        self, state: str, scopes: list[str], redirect_uri: str, code_challenge: str | None = None
    ) -> str:
        extra = {**self.extra_auth_params, "token_access_type": "offline"}
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
        data = {"code": code, "grant_type": "authorization_code", "redirect_uri": redirect_uri}
        if code_verifier:
            data["code_verifier"] = code_verifier
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url, data=data,
                auth=httpx.BasicAuth(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token"),
            token_type=body.get("token_type", "bearer"),
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
            token_type=body.get("token_type", "bearer"),
            expires_in=body.get("expires_in"),
            raw_response=body,
        )

    async def revoke_token(self, token: str) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.dropboxapi.com/2/auth/token/revoke",
                headers={"Authorization": f"Bearer {token}"},
            )
            return resp.status_code == 200

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.dropboxapi.com/2/users/get_current_account",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=data.get("account_id", ""),
                email=data.get("email"),
                display_name=data.get("name", {}).get("display_name"),
            )
