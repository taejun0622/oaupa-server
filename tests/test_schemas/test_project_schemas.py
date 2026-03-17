import pytest
from pydantic import ValidationError

from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate


class TestProjectCreate:
    def test_valid(self):
        data = ProjectCreate(name="My Project", slug="my-project")
        assert data.name == "My Project"
        assert data.slug == "my-project"

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            ProjectCreate(slug="slug-only")

    def test_missing_slug(self):
        with pytest.raises(ValidationError):
            ProjectCreate(name="Name Only")


class TestProjectUpdate:
    def test_optional_name(self):
        data = ProjectUpdate()
        assert data.name is None

    def test_with_name(self):
        data = ProjectUpdate(name="New Name")
        assert data.name == "New Name"


class TestProjectResponse:
    def test_from_attributes(self):
        import uuid
        from datetime import datetime

        data = ProjectResponse(
            id=uuid.uuid4(),
            name="Test",
            slug="test",
            is_active=True,
            created_at=datetime.now(),
        )
        assert data.slug == "test"
