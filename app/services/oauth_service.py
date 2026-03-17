"""OAuth flow orchestration: authorize URL generation, callback handling."""

import hashlib
import base64
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.encryption import decrypt, encrypt, get_current_key_version
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.oauth_connection import OAuthConnection
from app.models.oauth_provider import OAuthProvider
from app.models.oauth_state import OAuthState
from app.models.token_vault import TokenVault
from app.models.user import User
from app.providers.base import OAuthProviderBase
from app.providers.registry import create_provider
from app.schemas.oauth import OAuthAuthorizeRequest, OAuthAuthorizeResponse


async def get_provider_instance(db: AsyncSession, provider_id: str) -> tuple[OAuthProvider, OAuthProviderBase]:
    result = await db.execute(
        select(OAuthProvider).where(OAuthProvider.id == provider_id, OAuthProvider.is_active.is_(True))
    )
    provider_config = result.scalar_one_or_none()
    if provider_config is None:
        raise NotFoundError(f"Provider '{provider_id}' not found")

    client_secret = decrypt(provider_config.client_secret_encrypted)

    instance = create_provider(
        provider_id=provider_config.id,
        client_id=provider_config.client_id,
        client_secret=client_secret,
        auth_url=provider_config.auth_url,
        token_url=provider_config.token_url,
        revoke_url=provider_config.revoke_url,
        default_scopes=provider_config.default_scopes,
        extra_auth_params=provider_config.extra_auth_params,
    )
    return provider_config, instance


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    code_verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


async def start_oauth_flow(
    db: AsyncSession,
    user_id: uuid.UUID,
    data: OAuthAuthorizeRequest,
) -> OAuthAuthorizeResponse:
    provider_config, provider_instance = await get_provider_instance(db, data.provider_id)

    state_token = secrets.token_hex(32)
    scopes = data.scopes or provider_config.default_scopes

    # Generate PKCE
    code_verifier, code_challenge = _generate_pkce()

    callback_uri = settings.oauth_callback_base_url

    authorization_url = provider_instance.get_authorization_url(
        state=state_token,
        scopes=scopes,
        redirect_uri=callback_uri,
        code_challenge=code_challenge,
    )

    # Store state
    oauth_state = OAuthState(
        state_token=state_token,
        project_id=data.project_id,
        user_id=user_id,
        provider_id=data.provider_id,
        requested_scopes=scopes,
        redirect_uri=data.redirect_uri,
        code_verifier=code_verifier,
        metadata_=data.metadata or {},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    db.add(oauth_state)
    await db.flush()

    return OAuthAuthorizeResponse(authorization_url=authorization_url, state=state_token)


async def handle_oauth_callback(
    db: AsyncSession, code: str, state: str
) -> tuple[OAuthConnection, str]:
    """Process OAuth callback. Returns (connection, redirect_uri)."""
    # Look up state
    result = await db.execute(
        select(OAuthState).where(
            OAuthState.state_token == state,
            OAuthState.consumed_at.is_(None),
        )
    )
    oauth_state = result.scalar_one_or_none()
    if oauth_state is None:
        raise BadRequestError("Invalid or expired OAuth state")

    if oauth_state.expires_at < datetime.now(timezone.utc):
        raise BadRequestError("OAuth state expired")

    # Mark consumed
    oauth_state.consumed_at = datetime.now(timezone.utc)

    # Get provider
    provider_config, provider_instance = await get_provider_instance(db, oauth_state.provider_id)

    callback_uri = settings.oauth_callback_base_url

    # Check connection limit before creating
    from app.services import billing_service
    user_result = await db.execute(
        select(User).where(User.id == oauth_state.user_id)
    )
    user = user_result.scalar_one()
    await billing_service.check_connection_limit(db, user)

    # Exchange code for tokens
    token_response = await provider_instance.exchange_code(
        code=code,
        redirect_uri=callback_uri,
        code_verifier=oauth_state.code_verifier,
    )

    # Try to get account info
    account_info = await provider_instance.get_account_info(token_response.access_token)

    # Create connection
    connection = OAuthConnection(
        project_id=oauth_state.project_id,
        user_id=oauth_state.user_id,
        provider_id=oauth_state.provider_id,
        provider_account_id=account_info.account_id if account_info else None,
        provider_account_email=account_info.email if account_info else None,
        scopes_granted=oauth_state.requested_scopes,
        status="active",
    )
    db.add(connection)
    await db.flush()

    # Store tokens encrypted
    key_version = get_current_key_version()
    vault = TokenVault(
        connection_id=connection.id,
        access_token_encrypted=encrypt(token_response.access_token, key_version),
        refresh_token_encrypted=(
            encrypt(token_response.refresh_token, key_version)
            if token_response.refresh_token
            else None
        ),
        token_type=token_response.token_type,
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=token_response.expires_in)
            if token_response.expires_in
            else None
        ),
        raw_token_response_encrypted=(
            encrypt(str(token_response.raw_response), key_version)
            if token_response.raw_response
            else None
        ),
        encryption_key_id=key_version,
    )
    db.add(vault)
    await db.flush()

    # Fire webhook event
    from app.services.webhook_event_service import fire_webhook_event
    await fire_webhook_event(db, oauth_state.project_id, "connection.created", {
        "connection_id": str(connection.id),
        "provider_id": connection.provider_id,
        "provider_account_email": account_info.email if account_info else None,
    })

    # Build redirect URI with connection_id
    redirect_uri = oauth_state.redirect_uri
    separator = "&" if "?" in redirect_uri else "?"
    redirect_uri = f"{redirect_uri}{separator}connection_id={connection.id}"

    return connection, redirect_uri
