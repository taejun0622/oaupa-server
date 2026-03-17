"""Provider registry — maps provider IDs to implementation classes."""

from app.providers.base import OAuthProviderBase
from app.providers.google import GoogleProvider
from app.providers.github import GitHubProvider
from app.providers.slack import SlackProvider
from app.providers.microsoft import MicrosoftProvider
from app.providers.notion import NotionProvider
from app.providers.airtable import AirtableProvider
from app.providers.discord import DiscordProvider
from app.providers.gitlab import GitLabProvider
from app.providers.atlassian import AtlassianProvider
from app.providers.hubspot import HubSpotProvider
from app.providers.salesforce import SalesforceProvider
from app.providers.mailchimp import MailchimpProvider
from app.providers.stripe_provider import StripeOAuthProvider
from app.providers.paypal import PayPalProvider
from app.providers.square import SquareProvider
from app.providers.dropbox import DropboxProvider
from app.providers.box import BoxProvider
from app.providers.asana import AsanaProvider
from app.providers.trello import TrelloProvider
from app.providers.youtube import YouTubeProvider

PROVIDER_CLASSES: dict[str, type[OAuthProviderBase]] = {
    "google": GoogleProvider,
    "github": GitHubProvider,
    "slack": SlackProvider,
    "microsoft": MicrosoftProvider,
    "notion": NotionProvider,
    "airtable": AirtableProvider,
    "discord": DiscordProvider,
    "gitlab": GitLabProvider,
    "atlassian": AtlassianProvider,
    "hubspot": HubSpotProvider,
    "salesforce": SalesforceProvider,
    "mailchimp": MailchimpProvider,
    "stripe": StripeOAuthProvider,
    "paypal": PayPalProvider,
    "square": SquareProvider,
    "dropbox": DropboxProvider,
    "box": BoxProvider,
    "asana": AsanaProvider,
    "trello": TrelloProvider,
    "youtube": YouTubeProvider,
}


def get_provider_class(provider_id: str) -> type[OAuthProviderBase] | None:
    return PROVIDER_CLASSES.get(provider_id)


def create_provider(
    provider_id: str,
    client_id: str,
    client_secret: str,
    auth_url: str,
    token_url: str,
    revoke_url: str | None = None,
    default_scopes: list[str] | None = None,
    extra_auth_params: dict | None = None,
) -> OAuthProviderBase:
    cls = get_provider_class(provider_id)
    if cls is None:
        raise ValueError(f"Unknown provider: {provider_id}")
    return cls(
        client_id=client_id,
        client_secret=client_secret,
        auth_url=auth_url,
        token_url=token_url,
        revoke_url=revoke_url,
        default_scopes=default_scopes,
        extra_auth_params=extra_auth_params,
    )
