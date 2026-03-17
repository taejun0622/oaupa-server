import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.project import Project
from app.models.user import User
from app.schemas.project import ProjectCreate
from app.services import project_service


@pytest.mark.asyncio
class TestCreateProject:
    async def test_success(self, db: AsyncSession, test_user: User):
        slug = f"proj-{uuid.uuid4().hex[:8]}"
        data = ProjectCreate(name="My Project", slug=slug)
        project = await project_service.create_project(db, test_user.id, data)
        assert project.name == "My Project"
        assert project.slug == slug
        assert project.user_id == test_user.id

    async def test_duplicate_slug(self, db: AsyncSession, test_user: User):
        slug = f"dup-{uuid.uuid4().hex[:8]}"
        data = ProjectCreate(name="P1", slug=slug)
        await project_service.create_project(db, test_user.id, data)
        with pytest.raises(ConflictError):
            await project_service.create_project(db, test_user.id, data)


@pytest.mark.asyncio
class TestListProjects:
    async def test_returns_active_only(self, db: AsyncSession, test_user: User):
        # Create active project
        slug1 = f"active-{uuid.uuid4().hex[:8]}"
        data1 = ProjectCreate(name="Active", slug=slug1)
        await project_service.create_project(db, test_user.id, data1)

        # Create and soft-delete a project
        slug2 = f"deleted-{uuid.uuid4().hex[:8]}"
        data2 = ProjectCreate(name="Deleted", slug=slug2)
        deleted = await project_service.create_project(db, test_user.id, data2)
        await project_service.delete_project(db, deleted)

        projects = await project_service.list_projects(db, test_user.id)
        slugs = [p.slug for p in projects]
        assert slug1 in slugs
        assert slug2 not in slugs


@pytest.mark.asyncio
class TestGetProject:
    async def test_success(self, db: AsyncSession, test_user: User, test_project: Project):
        project = await project_service.get_project(db, test_project.id, test_user.id)
        assert project.id == test_project.id

    async def test_wrong_user(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await project_service.get_project(db, test_project.id, uuid.uuid4())

    async def test_nonexistent(self, db: AsyncSession, test_user: User):
        with pytest.raises(NotFoundError):
            await project_service.get_project(db, uuid.uuid4(), test_user.id)


@pytest.mark.asyncio
class TestUpdateProject:
    async def test_update_name(self, db: AsyncSession, test_project: Project):
        updated = await project_service.update_project(db, test_project, "Renamed")
        assert updated.name == "Renamed"


@pytest.mark.asyncio
class TestDeleteProject:
    async def test_soft_delete(self, db: AsyncSession, test_user: User):
        slug = f"todel-{uuid.uuid4().hex[:8]}"
        data = ProjectCreate(name="ToDelete", slug=slug)
        project = await project_service.create_project(db, test_user.id, data)
        await project_service.delete_project(db, project)
        assert project.is_active is False
