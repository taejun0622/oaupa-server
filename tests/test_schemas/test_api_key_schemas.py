import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.api_key import ApiKeyCreate, ApiKeyCreated, ApiKeyResponse


class TestApiKeyCreate:
    def test_defaults(self):
        data = ApiKeyCreate(name="Test")
        assert data.name == "Test"
        assert data.scopes == ["tokens:read"]
        assert data.expires_at is None

    def test_custom_scopes(self):
        data = ApiKeyCreate(name="X", scopes=["tokens:read", "connections:write"])
        assert len(data.scopes) == 2

    def test_missing_name(self):
        with pytest.raises(ValidationError):
            ApiKeyCreate()


class TestApiKeyResponse:
    def test_from_attributes(self):
        data = ApiKeyResponse(
            id=uuid.uuid4(),
            name="Key",
            key_prefix="oau_live_ab",
            scopes=["tokens:read"],
            last_used_at=None,
            expires_at=None,
            is_active=True,
            created_at=datetime.now(),
        )
        assert data.is_active is True
        assert "full_key" not in data.model_fields


class TestApiKeyCreated:
    def test_includes_full_key(self):
        data = ApiKeyCreated(
            id=uuid.uuid4(),
            name="Key",
            key_prefix="oau_live_ab",
            scopes=["tokens:read"],
            last_used_at=None,
            expires_at=None,
            is_active=True,
            created_at=datetime.now(),
            full_key="oau_live_abc123xyz",
        )
        assert data.full_key == "oau_live_abc123xyz"
