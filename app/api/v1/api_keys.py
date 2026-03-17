import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyResponse
from app.services import api_key_service
from app.services.audit_service import log_action

router = APIRouter()


@router.get(
    "/projects/{project_id}/api-keys",
    response_model=list[ApiKeyResponse],
)
async def list_api_keys(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    return await api_key_service.list_api_keys(db, project.id)


@router.post(
    "/projects/{project_id}/api-keys",
    response_model=ApiKeyCreated,
    status_code=201,
)
async def create_api_key(
    data: ApiKeyCreate,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    api_key, full_key = await api_key_service.create_api_key(db, project.id, data)
    await log_action(
        db, "api_key.created",
        user_id=user.id,
        project_id=project.id,
        resource_type="api_key",
        resource_id=api_key.id,
    )
    return ApiKeyCreated(
        id=api_key.id,
        name=api_key.name,
        key_prefix=api_key.key_prefix,
        scopes=api_key.scopes,
        last_used_at=api_key.last_used_at,
        expires_at=api_key.expires_at,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        full_key=full_key,
    )


@router.delete(
    "/projects/{project_id}/api-keys/{key_id}",
    status_code=204,
)
async def revoke_api_key(
    key_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await api_key_service.revoke_api_key(db, key_id, project.id)
    await log_action(
        db, "api_key.revoked",
        user_id=user.id,
        project_id=project.id,
        resource_type="api_key",
        resource_id=key_id,
    )
