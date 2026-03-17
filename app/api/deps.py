import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.models.api_key import ApiKey
from app.models.project import Project


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str = Header(..., alias="Authorization"),
) -> User:
    if not authorization.startswith("Bearer "):
        raise UnauthorizedError("Invalid authorization header")

    token = authorization[7:]
    payload = decode_token(token)
    if payload is None or payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")

    user_id = payload.get("sub")
    if user_id is None:
        raise UnauthorizedError("Invalid token payload")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return user


async def get_current_superadmin(
    user: User = Depends(get_current_user),
) -> User:
    if not user.is_superadmin:
        raise ForbiddenError("Superadmin access required")
    return user


async def resolve_api_key(
    db: AsyncSession = Depends(get_db),
    x_api_key: str = Header(..., alias="X-API-Key"),
) -> tuple[ApiKey, Project]:
    key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()

    result = await db.execute(
        select(ApiKey).where(ApiKey.key_hash == key_hash, ApiKey.is_active.is_(True))
    )
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise UnauthorizedError("Invalid API key")

    if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
        raise UnauthorizedError("API key expired")

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)

    result = await db.execute(select(Project).where(Project.id == api_key.project_id))
    project = result.scalar_one_or_none()
    if project is None or not project.is_active:
        raise UnauthorizedError("Project not found or inactive")

    return api_key, project


def require_scope(scope: str):
    """Dependency factory that checks the API key has the required scope."""

    async def _check(
        api_key_project: tuple[ApiKey, Project] = Depends(resolve_api_key),
    ) -> tuple[ApiKey, Project]:
        api_key, project = api_key_project
        if scope not in (api_key.scopes or []):
            raise ForbiddenError(f"API key missing required scope: {scope}")
        return api_key, project

    return _check


async def get_project_for_user(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user.id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        from app.core.exceptions import NotFoundError
        raise NotFoundError("Project not found")
    return project
