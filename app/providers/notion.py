import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url


class NotionProvider(OAuthProviderBase):
    provider_id = "notion"

    def get_authorization_url(
        self, state: str, scopes: list[str], redirect_uri: str, code_challenge: str | None = None
    ) -> str:
        extra = {**self.extra_auth_params, "owner": "user"}
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
                json={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
                auth=httpx.BasicAuth(self.client_id, self.client_secret),
            )
            resp.raise_for_status()
            body = resp.json()
        return TokenResponse(
            access_token=body["access_token"],
            token_type=body.get("token_type", "bearer"),
            raw_response=body,
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        raise NotImplementedError("Notion tokens do not expire and cannot be refreshed")

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.notion.com/v1/users/me",
                headers={"Authorization": f"Bearer {access_token}", "Notion-Version": "2022-06-28"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            bot = data.get("bot", {})
            owner = bot.get("owner", {}).get("user", {})
            return AccountInfo(
                account_id=data.get("id", ""),
                email=owner.get("person", {}).get("email"),
                display_name=owner.get("name"),
            )
