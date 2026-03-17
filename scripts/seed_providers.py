"""Seed OAuth provider configurations into the database.

Usage: python -m scripts.seed_providers
Requires OAUPA_MASTER_KEY to be set for encrypting client secrets.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from app.core.encryption import encrypt
from app.db.session import async_session_factory
from app.models.oauth_provider import OAuthProvider

PROVIDERS = [
    {
        "id": "google",
        "display_name": "Google",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "default_scopes": ["openid", "email", "profile"],
        "extra_auth_params": {"access_type": "offline", "prompt": "consent"},
        "supports_refresh": True,
    },
    {
        "id": "microsoft",
        "display_name": "Microsoft",
        "auth_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "default_scopes": ["openid", "email", "profile", "offline_access"],
        "supports_refresh": True,
    },
    {
        "id": "notion",
        "display_name": "Notion",
        "auth_url": "https://api.notion.com/v1/oauth/authorize",
        "token_url": "https://api.notion.com/v1/oauth/token",
        "default_scopes": [],
        "extra_auth_params": {"owner": "user"},
        "supports_refresh": False,
    },
    {
        "id": "airtable",
        "display_name": "Airtable",
        "auth_url": "https://airtable.com/oauth2/v1/authorize",
        "token_url": "https://airtable.com/oauth2/v1/token",
        "default_scopes": ["data.records:read", "data.records:write", "schema.bases:read"],
        "supports_refresh": True,
    },
    {
        "id": "slack",
        "display_name": "Slack",
        "auth_url": "https://slack.com/oauth/v2/authorize",
        "token_url": "https://slack.com/api/oauth.v2.access",
        "revoke_url": "https://slack.com/api/auth.revoke",
        "default_scopes": ["users:read", "channels:read"],
        "supports_refresh": True,
    },
    {
        "id": "discord",
        "display_name": "Discord",
        "auth_url": "https://discord.com/api/oauth2/authorize",
        "token_url": "https://discord.com/api/oauth2/token",
        "revoke_url": "https://discord.com/api/oauth2/token/revoke",
        "default_scopes": ["identify", "email"],
        "supports_refresh": True,
    },
    {
        "id": "github",
        "display_name": "GitHub",
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "revoke_url": "https://api.github.com/applications",
        "default_scopes": ["read:user", "user:email"],
        "supports_refresh": False,
    },
    {
        "id": "gitlab",
        "display_name": "GitLab",
        "auth_url": "https://gitlab.com/oauth/authorize",
        "token_url": "https://gitlab.com/oauth/token",
        "default_scopes": ["read_user", "api"],
        "supports_refresh": True,
    },
    {
        "id": "atlassian",
        "display_name": "Atlassian (Jira/Confluence)",
        "auth_url": "https://auth.atlassian.com/authorize",
        "token_url": "https://auth.atlassian.com/oauth/token",
        "default_scopes": ["read:me", "read:jira-work", "read:confluence-content.all"],
        "extra_auth_params": {"audience": "api.atlassian.com", "prompt": "consent"},
        "supports_refresh": True,
    },
    {
        "id": "hubspot",
        "display_name": "HubSpot",
        "auth_url": "https://app.hubspot.com/oauth/authorize",
        "token_url": "https://api.hubapi.com/oauth/v1/token",
        "default_scopes": ["crm.objects.contacts.read"],
        "supports_refresh": True,
    },
    {
        "id": "salesforce",
        "display_name": "Salesforce",
        "auth_url": "https://login.salesforce.com/services/oauth2/authorize",
        "token_url": "https://login.salesforce.com/services/oauth2/token",
        "revoke_url": "https://login.salesforce.com/services/oauth2/revoke",
        "default_scopes": ["full", "refresh_token"],
        "supports_refresh": True,
    },
    {
        "id": "mailchimp",
        "display_name": "Mailchimp",
        "auth_url": "https://login.mailchimp.com/oauth2/authorize",
        "token_url": "https://login.mailchimp.com/oauth2/token",
        "default_scopes": [],
        "supports_refresh": False,
    },
    {
        "id": "stripe",
        "display_name": "Stripe",
        "auth_url": "https://connect.stripe.com/oauth/authorize",
        "token_url": "https://connect.stripe.com/oauth/token",
        "revoke_url": "https://connect.stripe.com/oauth/deauthorize",
        "default_scopes": ["read_write"],
        "supports_refresh": True,
    },
    {
        "id": "paypal",
        "display_name": "PayPal",
        "auth_url": "https://www.paypal.com/signin/authorize",
        "token_url": "https://api.paypal.com/v1/oauth2/token",
        "default_scopes": ["openid", "email"],
        "supports_refresh": True,
    },
    {
        "id": "square",
        "display_name": "Square",
        "auth_url": "https://connect.squareup.com/oauth2/authorize",
        "token_url": "https://connect.squareup.com/oauth2/token",
        "revoke_url": "https://connect.squareup.com/oauth2/revoke",
        "default_scopes": ["MERCHANT_PROFILE_READ", "PAYMENTS_READ"],
        "supports_refresh": True,
    },
    {
        "id": "dropbox",
        "display_name": "Dropbox",
        "auth_url": "https://www.dropbox.com/oauth2/authorize",
        "token_url": "https://api.dropboxapi.com/oauth2/token",
        "default_scopes": [],
        "extra_auth_params": {"token_access_type": "offline"},
        "supports_refresh": True,
    },
    {
        "id": "box",
        "display_name": "Box",
        "auth_url": "https://account.box.com/api/oauth2/authorize",
        "token_url": "https://api.box.com/oauth2/token",
        "revoke_url": "https://api.box.com/oauth2/revoke",
        "default_scopes": [],
        "supports_refresh": True,
    },
    {
        "id": "asana",
        "display_name": "Asana",
        "auth_url": "https://app.asana.com/-/oauth_authorize",
        "token_url": "https://app.asana.com/-/oauth_token",
        "default_scopes": ["default"],
        "supports_refresh": True,
    },
    {
        "id": "trello",
        "display_name": "Trello",
        "auth_url": "https://trello.com/1/authorize",
        "token_url": "https://trello.com/1/OAuthGetAccessToken",
        "default_scopes": ["read", "write"],
        "extra_auth_params": {"expiration": "never"},
        "supports_refresh": False,
    },
    {
        "id": "youtube",
        "display_name": "YouTube",
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "revoke_url": "https://oauth2.googleapis.com/revoke",
        "default_scopes": ["https://www.googleapis.com/auth/youtube.readonly"],
        "extra_auth_params": {"access_type": "offline", "prompt": "consent"},
        "supports_refresh": True,
    },
]


async def seed():
    async with async_session_factory() as session:
        for provider_data in PROVIDERS:
            result = await session.execute(
                select(OAuthProvider).where(OAuthProvider.id == provider_data["id"])
            )
            existing = result.scalar_one_or_none()
            if existing:
                print(f"  Skipping {provider_data['id']} (already exists)")
                continue

            # Use placeholder client_id/secret — admin must configure real values
            provider = OAuthProvider(
                id=provider_data["id"],
                display_name=provider_data["display_name"],
                auth_url=provider_data["auth_url"],
                token_url=provider_data["token_url"],
                revoke_url=provider_data.get("revoke_url"),
                client_id="CONFIGURE_ME",
                client_secret_encrypted=encrypt("CONFIGURE_ME"),
                default_scopes=provider_data.get("default_scopes", []),
                extra_auth_params=provider_data.get("extra_auth_params", {}),
                supports_refresh=provider_data.get("supports_refresh", True),
            )
            session.add(provider)
            print(f"  Added {provider_data['id']}")

        await session.commit()
        print("Done!")


if __name__ == "__main__":
    asyncio.run(seed())
