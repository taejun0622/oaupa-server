import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.oauth_connection import OAuthConnection
from app.services.oauth_service import get_provider_instance
from app.core.encryption import decrypt


async def list_connections(
    db: AsyncSession, project_id: uuid.UUID
) -> list[OAuthConnection]:
    result = await db.execute(
        select(OAuthConnection).where(OAuthConnection.project_id == project_id)
    )
    return list(result.scalars().all())


async def get_connection(
    db: AsyncSession, project_id: uuid.UUID, connection_id: uuid.UUID
) -> OAuthConnection:
    result = await db.execute(
        select(OAuthConnection).where(
            OAuthConnection.id == connection_id,
            OAuthConnection.project_id == project_id,
        )
    )
    connection = result.scalar_one_or_none()
    if connection is None:
        raise NotFoundError("Connection not found")
    return connection


async def revoke_connection(
    db: AsyncSession, project_id: uuid.UUID, connection_id: uuid.UUID
) -> None:
    from sqlalchemy.orm import joinedload

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

    # Try to revoke at provider
    if connection.token_vault:
        try:
            _provider_config, provider_instance = await get_provider_instance(
                db, connection.provider_id
            )
            access_token = decrypt(connection.token_vault.access_token_encrypted)
            await provider_instance.revoke_token(access_token)
        except Exception:
            pass  # Best-effort revocation

    connection.status = "revoked"
    await db.flush()

    from app.services.webhook_event_service import fire_webhook_event
    await fire_webhook_event(db, project_id, "connection.revoked", {
        "connection_id": str(connection_id),
        "provider_id": connection.provider_id,
    })
