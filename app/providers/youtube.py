"""YouTube uses Google's OAuth2. Shares the same flow as Google, but with YouTube-specific scopes."""

from app.providers.google import GoogleProvider
from app.providers.base import AccountInfo

import httpx


class YouTubeProvider(GoogleProvider):
    provider_id = "youtube"

    async def get_account_info(self, access_token: str) -> AccountInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://www.googleapis.com/youtube/v3/channels",
                params={"part": "snippet", "mine": "true"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            items = data.get("items", [])
            if not items:
                return None
            channel = items[0]
            snippet = channel.get("snippet", {})
            return AccountInfo(
                account_id=channel.get("id", ""),
                email=None,
                display_name=snippet.get("title"),
            )
