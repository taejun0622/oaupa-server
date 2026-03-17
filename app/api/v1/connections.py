import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_project_for_user
from app.db.session import get_db
from app.models.project import Project
from app.models.user import User
from app.schemas.connection import ConnectionResponse, TokenRetrievalResponse
from app.services import connection_service, token_vault_service
from app.services.audit_service import log_action

router = APIRouter()


@router.get(
    "/projects/{project_id}/connections",
    response_model=list[ConnectionResponse],
)
async def list_connections(
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    return await connection_service.list_connections(db, project.id)


@router.get(
    "/projects/{project_id}/connections/{connection_id}",
    response_model=ConnectionResponse,
)
async def get_connection(
    connection_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    return await connection_service.get_connection(db, project.id, connection_id)


@router.delete(
    "/projects/{project_id}/connections/{connection_id}",
    status_code=204,
)
async def revoke_connection(
    connection_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await connection_service.revoke_connection(db, project.id, connection_id)
    await log_action(
        db, "connection.revoked",
        user_id=user.id,
        project_id=project.id,
        resource_type="connection",
        resource_id=connection_id,
    )


@router.post(
    "/projects/{project_id}/connections/{connection_id}/refresh",
    response_model=TokenRetrievalResponse,
)
async def force_refresh(
    connection_id: uuid.UUID,
    project: Project = Depends(get_project_for_user),
    db: AsyncSession = Depends(get_db),
):
    return await token_vault_service.force_refresh(db, project.id, connection_id)
