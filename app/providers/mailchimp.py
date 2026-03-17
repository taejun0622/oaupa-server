import httpx

from app.providers.base import AccountInfo, OAuthProviderBase, TokenResponse
from app.providers._http import build_authorization_url, exchange_code_standard


class MailchimpProvider(OAuthProviderBase):
    provider_id = "mailchimp"

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
        return await exchange_code_standard(
            self.token_url, self.client_id, self.client_secret, code, redirect_uri, code_verifier
        )

    async def refresh_token(self, refresh_token: str) -> TokenResponse:
        raise NotImplementedError("Mailchimp tokens do not expire")

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://login.mailchimp.com/oauth2/metadata",
                headers={"Authorization": f"OAuth {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return AccountInfo(
                account_id=data.get("user_id", ""),
                email=data.get("login", {}).get("email"),
                display_name=data.get("accountname"),
            )
