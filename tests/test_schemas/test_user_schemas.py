import pytest
from pydantic import ValidationError

from app.schemas.user import TokenPair, UserLogin, UserRegister, UserResponse


class TestUserRegister:
    def test_valid(self):
        data = UserRegister(email="test@example.com", password="secure123")
        assert data.email == "test@example.com"

    def test_with_name(self):
        data = UserRegister(email="a@b.com", password="pass", full_name="John")
        assert data.full_name == "John"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserRegister(email="not-email", password="pass")

    def test_missing_password(self):
        with pytest.raises(ValidationError):
            UserRegister(email="a@b.com")


class TestUserLogin:
    def test_valid(self):
        data = UserLogin(email="test@test.com", password="pass")
        assert data.password == "pass"

    def test_invalid_email(self):
        with pytest.raises(ValidationError):
            UserLogin(email="bad", password="pass")


class TestTokenPair:
    def test_defaults(self):
        data = TokenPair(access_token="at", refresh_token="rt")
        assert data.token_type == "bearer"


class TestUserResponse:
    def test_from_attributes(self):
        import uuid
        from datetime import datetime

        data = UserResponse(
            id=uuid.uuid4(),
            email="x@y.com",
            full_name=None,
            is_active=True,
            email_verified_at=None,
            created_at=datetime.now(),
        )
        assert data.email == "x@y.com"
