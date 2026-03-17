import os
from datetime import timedelta

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key")

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        hashed = hash_password("mypassword")
        assert verify_password("mypassword", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("mypassword")
        assert verify_password("wrongpassword", hashed) is False

    def test_different_hashes(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt uses random salt


class TestJWT:
    def test_create_access_token(self):
        token = create_access_token("user-123")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["type"] == "access"
        assert "exp" in payload

    def test_create_refresh_token(self):
        token = create_refresh_token("user-123")
        payload = decode_token(token)
        assert payload is not None
        assert payload["sub"] == "user-123"
        assert payload["type"] == "refresh"

    def test_custom_expiry(self):
        token = create_access_token("user-123", expires_delta=timedelta(minutes=5))
        payload = decode_token(token)
        assert payload is not None

    def test_decode_invalid_token(self):
        assert decode_token("not-a-valid-token") is None

    def test_decode_empty_token(self):
        assert decode_token("") is None

    def test_decode_garbage(self):
        assert decode_token("eyJhbGciOiJIUzI1NiJ9.garbage.garbage") is None
