import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url, exchange_code_standard


class GitHubProvider(OAuthProviderBase):
    provider_id = "github"

    def get_authorization_url(
        self,
        state: str,
        scopes: list[str],
        redirect_uri: str,
        code_challenge: str | None = None,
    ) -> str:
        return build_authorization_url(
            auth_url=self.auth_url,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes or self.default_scopes,
            code_challenge=code_challenge,
            extra_params=self.extra_auth_params,
            scope_separator=",",
        )

    async def exchange_code(
        self, code: str, redirect_uri: str, code_verifier: str | None = None
    ) -> TokenResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                },
                headers={"Accept": "application/json"},
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
        # GitHub tokens don't expire by default; refresh is only for GitHub Apps
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={"Accept": "application/json"},
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
        if not self.revoke_url:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{self.revoke_url}/{self.client_id}/token",
                auth=httpx.BasicAuth(self.client_id, self.client_secret),
                json={"access_token": token},
            )
            return resp.status_code == 204

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github+json",
                },
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=str(data.get("id", "")),
                email=data.get("email"),
                display_name=data.get("login"),
            )
