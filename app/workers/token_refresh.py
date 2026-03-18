"""Background token refresh worker.

Proactively refreshes tokens before they expire.
Uses SELECT ... FOR UPDATE SKIP LOCKED for safe concurrency.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.core.encryption import decrypt, encrypt, get_current_key_version
from app.models.oauth_connection import OAuthConnection
from app.models.oauth_provider import OAuthProvider
from app.models.oauth_state import OAuthState
from app.models.token_vault import TokenVault
from app.providers.registry import create_provider
from app.workers.celery_app import celery_app


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_session_factory() -> async_sessionmaker[AsyncSession]:
    """Create a fresh engine + session factory for each task to avoid event loop conflicts."""
    engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@celery_app.task(name="app.workers.token_refresh.refresh_expiring_tokens")
def refresh_expiring_tokens():
    _run_async(_refresh_expiring_tokens())


async def _refresh_expiring_tokens():
    session_factory = _make_session_factory()
    async with session_factory() as session:
        # Find tokens expiring within their provider's buffer time
        now = datetime.now(timezone.utc)

        result = await session.execute(
            select(TokenVault)
            .join(OAuthConnection, TokenVault.connection_id == OAuthConnection.id)
            .where(
                OAuthConnection.status == "active",
                TokenVault.expires_at.isnot(None),
                TokenVault.expires_at < now + timedelta(minutes=5),
                TokenVault.refresh_token_encrypted.isnot(None),
            )
            .with_for_update(skip_locked=True)
            .limit(50)
        )
        vaults = result.scalars().all()

        for vault in vaults:
            try:
                await _refresh_single_token(session, vault)
            except Exception as e:
                print(f"Failed to refresh token for connection {vault.connection_id}: {e}")

        await session.commit()


async def _refresh_single_token(session, vault: TokenVault):
    # Load connection and provider
    conn_result = await session.execute(
        select(OAuthConnection).where(OAuthConnection.id == vault.connection_id)
    )
    connection = conn_result.scalar_one()

    prov_result = await session.execute(
        select(OAuthProvider).where(OAuthProvider.id == connection.provider_id)
    )
    provider_config = prov_result.scalar_one()

    client_secret = decrypt(provider_config.client_secret_encrypted)
    provider_instance = create_provider(
        provider_id=provider_config.id,
        client_id=provider_config.client_id,
        client_secret=client_secret,
        auth_url=provider_config.auth_url,
        token_url=provider_config.token_url,
        revoke_url=provider_config.revoke_url,
        default_scopes=provider_config.default_scopes,
        extra_auth_params=provider_config.extra_auth_params,
    )

    refresh_token = decrypt(vault.refresh_token_encrypted)

    try:
        token_response = await provider_instance.refresh_token(refresh_token)
    except Exception as e:
        connection.status = "error"
        connection.status_detail = f"Background refresh failed: {e}"
        return

    key_version = get_current_key_version()
    vault.access_token_encrypted = encrypt(token_response.access_token, key_version)
    if token_response.refresh_token:
        vault.refresh_token_encrypted = encrypt(token_response.refresh_token, key_version)
    vault.encryption_key_id = key_version
    if token_response.expires_in:
        vault.expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_response.expires_in)
    connection.last_refreshed_at = datetime.now(timezone.utc)


@celery_app.task(name="app.workers.token_refresh.cleanup_expired_states")
def cleanup_expired_states():
    _run_async(_cleanup_expired_states())


async def _cleanup_expired_states():
    session_factory = _make_session_factory()
    async with session_factory() as session:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        await session.execute(
            delete(OAuthState).where(OAuthState.expires_at < cutoff)
        )
        await session.commit()
