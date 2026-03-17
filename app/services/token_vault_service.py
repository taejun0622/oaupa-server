"""Token vault service: retrieve and refresh tokens."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.encryption import decrypt, encrypt, get_current_key_version
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.oauth_connection import OAuthConnection
from app.models.token_vault import TokenVault
from app.schemas.connection import TokenRetrievalResponse
from app.services.oauth_service import get_provider_instance


async def get_token(
    db: AsyncSession,
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> TokenRetrievalResponse:
    result = await db.execute(
        select(OAuthConnection)
        .options(joinedload(OAuthConnection.token_vault))
        .where(
            OAuthConnection.id == connection_id,
            OAuthConnection.project_id == project_id,
        )
    )
    connection = result.unique().scalar_one_or_none()
    if connection is None:
        raise NotFoundError("Connection not found")

    if connection.status != "active":
        raise BadRequestError(f"Connection is {connection.status}: {connection.status_detail or ''}")

    vault = connection.token_vault
    if vault is None:
        raise NotFoundError("No tokens found for this connection")

    # Check if token needs refresh (within 30 seconds of expiry)
    if vault.expires_at and vault.expires_at < datetime.now(timezone.utc) + timedelta(seconds=30):
        vault = await _refresh_token_inline(db, connection, vault)

    access_token = decrypt(vault.access_token_encrypted)

    return TokenRetrievalResponse(
        access_token=access_token,
        token_type=vault.token_type,
        expires_at=vault.expires_at,
        connection_id=connection.id,
        provider=connection.provider_id,
    )


async def get_token_by_provider(
    db: AsyncSession,
    project_id: uuid.UUID,
    provider_id: str,
) -> TokenRetrievalResponse:
    result = await db.execute(
        select(OAuthConnection)
        .options(joinedload(OAuthConnection.token_vault))
        .where(
            OAuthConnection.project_id == project_id,
            OAuthConnection.provider_id == provider_id,
            OAuthConnection.status == "active",
        )
        .limit(1)
    )
    connection = result.unique().scalar_one_or_none()
    if connection is None:
        raise NotFoundError(f"No active connection for provider '{provider_id}'")

    return await get_token(db, project_id, connection.id)


async def _refresh_token_inline(
    db: AsyncSession,
    connection: OAuthConnection,
    vault: TokenVault,
) -> TokenVault:
    if vault.refresh_token_encrypted is None:
        connection.status = "expired"
        connection.status_detail = "Access token expired and no refresh token available"
        await db.flush()
        from app.services.webhook_event_service import fire_webhook_event
        await fire_webhook_event(db, connection.project_id, "connection.error", {
            "connection_id": str(connection.id),
            "provider_id": connection.provider_id,
            "error": "Token expired and no refresh token available",
        })
        raise BadRequestError("Token expired and cannot be refreshed")

    refresh_token = decrypt(vault.refresh_token_encrypted)
    provider_config, provider_instance = await get_provider_instance(db, connection.provider_id)

    try:
        token_response = await provider_instance.refresh_token(refresh_token)
    except Exception as e:
        connection.status = "error"
        connection.status_detail = f"Token refresh failed: {e}"
        await db.flush()
        from app.services.webhook_event_service import fire_webhook_event
        await fire_webhook_event(db, connection.project_id, "connection.error", {
            "connection_id": str(connection.id),
            "provider_id": connection.provider_id,
            "error": str(e),
        })
        raise BadRequestError(f"Token refresh failed: {e}")

    key_version = get_current_key_version()
    vault.access_token_encrypted = encrypt(token_response.access_token, key_version)
    if token_response.refresh_token:
        vault.refresh_token_encrypted = encrypt(token_response.refresh_token, key_version)
    vault.encryption_key_id = key_version
    if token_response.expires_in:
        vault.expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_response.expires_in)
    connection.last_refreshed_at = datetime.now(timezone.utc)
    await db.flush()

    from app.services.webhook_event_service import fire_webhook_event
    await fire_webhook_event(db, connection.project_id, "connection.refreshed", {
        "connection_id": str(connection.id),
        "provider_id": connection.provider_id,
    })

    return vault


async def force_refresh(
    db: AsyncSession,
    project_id: uuid.UUID,
    connection_id: uuid.UUID,
) -> TokenRetrievalResponse:
    result = await db.execute(
        select(OAuthConnection)
        .options(joinedload(OAuthConnection.token_vault))
        .where(
            OAuthConnection.id == connection_id,
            OAuthConnection.project_id == project_id,
        )
    )
    connection = result.unique().scalar_one_or_none()
    if connection is None:
        raise NotFoundError("Connection not found")

    vault = connection.token_vault
    if vault is None:
        raise NotFoundError("No tokens found")

    vault = await _refresh_token_inline(db, connection, vault)
    access_token = decrypt(vault.access_token_encrypted)

    return TokenRetrievalResponse(
        access_token=access_token,
        token_type=vault.token_type,
        expires_at=vault.expires_at,
        connection_id=connection.id,
        provider=connection.provider_id,
    )
