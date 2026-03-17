import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url


class SlackProvider(OAuthProviderBase):
    provider_id = "slack"

    def get_authorization_url(
        self,
        state: str,
        scopes: list[str],
        redirect_uri: str,
        code_challenge: str | None = None,
    ) -> str:
        extra = {**self.extra_auth_params}
        # Slack uses user_scope for user tokens
        return build_authorization_url(
            auth_url=self.auth_url,
            client_id=self.client_id,
            redirect_uri=redirect_uri,
            state=state,
            scopes=scopes or self.default_scopes,
            code_challenge=code_challenge,
            extra_params=extra,
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
            )
            resp.raise_for_status()
            body = resp.json()

        if not body.get("ok"):
            raise ValueError(f"Slack token exchange failed: {body.get('error')}")

        # Slack returns authed_user for user tokens
        authed_user = body.get("authed_user", {})
        access_token = authed_user.get("access_token") or body.get("access_token")
        refresh_token = authed_user.get("refresh_token") or body.get("refresh_token")

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",
            expires_in=authed_user.get("expires_in") or body.get("expires_in"),
            scope=authed_user.get("scope") or body.get("scope"),
            raw_response=body,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.token_url,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
            )
            resp.raise_for_status()
            body = resp.json()

        if not body.get("ok"):
            raise ValueError(f"Slack token refresh failed: {body.get('error')}")

        return TokenResponse(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", refresh_token),
            token_type="Bearer",
            expires_in=body.get("expires_in"),
            raw_response=body,
        )

    async def revoke_token(self, token: str) -> bool:
        if not self.revoke_url:
            return False
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                self.revoke_url,
                headers={"Authorization": f"Bearer {token}"},
            )
            body = resp.json()
            return body.get("ok", False)

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://slack.com/api/users.identity",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            body = resp.json()
            if not body.get("ok"):
                return None
            user = body.get("user", {})
            return AccountInfo(
                account_id=user.get("id", ""),
                email=user.get("email"),
                display_name=user.get("name"),
            )
