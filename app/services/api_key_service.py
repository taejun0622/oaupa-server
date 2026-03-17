import hashlib
import secrets
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.api_key import ApiKey
from app.schemas.api_key import ApiKeyCreate


def generate_api_key() -> str:
    return f"oau_live_{secrets.token_urlsafe(30)}"


async def create_api_key(
    db: AsyncSession, project_id: uuid.UUID, data: ApiKeyCreate
) -> tuple[ApiKey, str]:
    full_key = generate_api_key()
    key_hash = hashlib.sha256(full_key.encode()).hexdigest()
    key_prefix = full_key[:12]

    api_key = ApiKey(
        project_id=project_id,
        name=data.name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        scopes=data.scopes,
        expires_at=data.expires_at,
    )
    db.add(api_key)
    await db.flush()
    return api_key, full_key


async def list_api_keys(db: AsyncSession, project_id: uuid.UUID) -> list[ApiKey]:
    result = await db.execute(
        select(ApiKey).where(ApiKey.project_id == project_id, ApiKey.is_active.is_(True))
    )
    return list(result.scalars().all())


async def revoke_api_key(
    db: AsyncSession, key_id: uuid.UUID, project_id: uuid.UUID
) -> None:
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.project_id == project_id)
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise NotFoundError("API key not found")
    api_key.is_active = False
    await db.flush()
