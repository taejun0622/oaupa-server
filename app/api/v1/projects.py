import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.services import project_service
from app.services.audit_service import log_action

router = APIRouter()


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await project_service.list_projects(db, user.id)


@router.post("", response_model=ProjectResponse, status_code=201)
async def create_project(
    data: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await project_service.create_project(db, user.id, data)
    await log_action(
        db, "project.created",
        user_id=user.id,
        project_id=project.id,
        resource_type="project",
        resource_id=project.id,
    )
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await project_service.get_project(db, project_id, user.id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    data: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await project_service.get_project(db, project_id, user.id)
    return await project_service.update_project(db, project, data.name)


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    project = await project_service.get_project(db, project_id, user.id)
    await log_action(
        db, "project.deleted",
        user_id=user.id,
        project_id=project.id,
        resource_type="project",
        resource_id=project.id,
    )
    await project_service.delete_project(db, project)
