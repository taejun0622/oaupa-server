import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.project import Project
from app.schemas.project import ProjectCreate


async def create_project(db: AsyncSession, user_id: uuid.UUID, data: ProjectCreate) -> Project:
    result = await db.execute(select(Project).where(Project.slug == data.slug))
    if result.scalar_one_or_none() is not None:
        raise ConflictError("Project slug already in use")

    project = Project(user_id=user_id, name=data.name, slug=data.slug)
    db.add(project)
    await db.flush()
    return project


async def list_projects(db: AsyncSession, user_id: uuid.UUID) -> list[Project]:
    result = await db.execute(
        select(Project).where(Project.user_id == user_id, Project.is_active.is_(True))
    )
    return list(result.scalars().all())


async def get_project(db: AsyncSession, project_id: uuid.UUID, user_id: uuid.UUID) -> Project:
    result = await db.execute(
        select(Project).where(Project.id == project_id, Project.user_id == user_id)
    )
    project = result.scalar_one_or_none()
    if project is None:
        raise NotFoundError("Project not found")
    return project


async def update_project(db: AsyncSession, project: Project, name: str | None) -> Project:
    if name is not None:
        project.name = name
    await db.flush()
    return project


async def delete_project(db: AsyncSession, project: Project) -> None:
    project.is_active = False
    await db.flush()
