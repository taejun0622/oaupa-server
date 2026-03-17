import hashlib
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.project import Project
from app.schemas.api_key import ApiKeyCreate
from app.services import api_key_service


class TestGenerateApiKey:
    def test_format(self):
        key = api_key_service.generate_api_key()
        assert key.startswith("oau_live_")
        assert len(key) > 20

    def test_unique(self):
        k1 = api_key_service.generate_api_key()
        k2 = api_key_service.generate_api_key()
        assert k1 != k2


@pytest.mark.asyncio
class TestCreateApiKey:
    async def test_success(self, db: AsyncSession, test_project: Project):
        data = ApiKeyCreate(name="Prod Key")
        api_key, full_key = await api_key_service.create_api_key(db, test_project.id, data)
        assert api_key.name == "Prod Key"
        assert full_key.startswith("oau_live_")
        assert api_key.key_prefix == full_key[:12]
        # Hash matches
        expected_hash = hashlib.sha256(full_key.encode()).hexdigest()
        assert api_key.key_hash == expected_hash

    async def test_default_scopes(self, db: AsyncSession, test_project: Project):
        data = ApiKeyCreate(name="Default")
        api_key, _ = await api_key_service.create_api_key(db, test_project.id, data)
        assert api_key.scopes == ["tokens:read"]

    async def test_custom_scopes(self, db: AsyncSession, test_project: Project):
        data = ApiKeyCreate(name="Custom", scopes=["tokens:read", "connections:write"])
        api_key, _ = await api_key_service.create_api_key(db, test_project.id, data)
        assert "connections:write" in api_key.scopes


@pytest.mark.asyncio
class TestListApiKeys:
    async def test_active_only(self, db: AsyncSession, test_project: Project):
        data1 = ApiKeyCreate(name="Active")
        data2 = ApiKeyCreate(name="ToRevoke")
        await api_key_service.create_api_key(db, test_project.id, data1)
        api_key2, _ = await api_key_service.create_api_key(db, test_project.id, data2)
        await api_key_service.revoke_api_key(db, api_key2.id, test_project.id)

        keys = await api_key_service.list_api_keys(db, test_project.id)
        names = [k.name for k in keys]
        assert "Active" in names
        assert "ToRevoke" not in names


@pytest.mark.asyncio
class TestRevokeApiKey:
    async def test_success(self, db: AsyncSession, test_project: Project):
        data = ApiKeyCreate(name="Revokable")
        api_key, _ = await api_key_service.create_api_key(db, test_project.id, data)
        await api_key_service.revoke_api_key(db, api_key.id, test_project.id)
        assert api_key.is_active is False

    async def test_not_found(self, db: AsyncSession, test_project: Project):
        with pytest.raises(NotFoundError):
            await api_key_service.revoke_api_key(db, uuid.uuid4(), test_project.id)

    async def test_wrong_project(self, db: AsyncSession, test_project: Project):
        data = ApiKeyCreate(name="WrongProj")
        api_key, _ = await api_key_service.create_api_key(db, test_project.id, data)
        with pytest.raises(NotFoundError):
            await api_key_service.revoke_api_key(db, api_key.id, uuid.uuid4())
