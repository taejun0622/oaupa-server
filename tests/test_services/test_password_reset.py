"""Tests for password reset and email verification flows."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.services import user_service
from tests.conftest import auth_headers


# ── Helpers ──────────────────────────────────────────────────────────


async def _create_user(db: AsyncSession, email: str = None, password: str = "testpassword123") -> User:
    user = User(
        email=email or f"reset-{uuid.uuid4().hex[:8]}@test.com",
        password_hash=hash_password(password),
        full_name="Test User",
    )
    db.add(user)
    await db.flush()
    return user


def _make_token(user_id: str, purpose: str, expires_delta: timedelta = None) -> str:
    """Create a JWT token for testing."""
    delta = expires_delta or timedelta(hours=1)
    return user_service._create_email_token(user_id, purpose, delta)


def _make_expired_token(user_id: str, purpose: str) -> str:
    """Create an expired JWT token for testing."""
    return user_service._create_email_token(user_id, purpose, timedelta(seconds=-1))


# ── Forgot Password ─────────────────────────────────────────────────


@pytest.mark.asyncio
class TestForgotPassword:
    async def test_valid_email_returns_200(self, client: AsyncClient, db: AsyncSession):
        """Existing user email returns success message."""
        user = await _create_user(db, "forgot@test.com")
        await db.commit()

        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "forgot@test.com"},
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    async def test_unknown_email_still_returns_200(self, client: AsyncClient):
        """Unknown email returns same message (prevents enumeration)."""
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert resp.status_code == 200
        assert "reset link" in resp.json()["message"].lower()

    async def test_invalid_email_format_returns_422(self, client: AsyncClient):
        """Malformed email returns validation error."""
        resp = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": "not-an-email"},
        )
        assert resp.status_code == 422

    async def test_empty_body_returns_422(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/forgot-password", json={})
        assert resp.status_code == 422


# ── Reset Password ──────────────────────────────────────────────────


@pytest.mark.asyncio
class TestResetPassword:
    async def test_valid_token_resets_password(self, db: AsyncSession, client: AsyncClient):
        """Valid reset token + new password succeeds."""
        user = await _create_user(db, password="oldpassword123")
        await db.commit()

        token = _make_token(str(user.id), "password_reset")

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpassword123"},
        )
        assert resp.status_code == 200
        assert "reset" in resp.json()["message"].lower()

        # Verify old password no longer works, new one does
        await db.refresh(user)
        assert not verify_password("oldpassword123", user.password_hash)
        assert verify_password("newpassword123", user.password_hash)

    async def test_expired_token_returns_400(self, db: AsyncSession, client: AsyncClient):
        """Expired token is rejected."""
        user = await _create_user(db)
        await db.commit()

        token = _make_expired_token(str(user.id), "password_reset")

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpassword123"},
        )
        assert resp.status_code == 400

    async def test_invalid_token_returns_400(self, client: AsyncClient):
        """Garbage token is rejected."""
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "completely-invalid-garbage", "new_password": "newpass123"},
        )
        assert resp.status_code == 400

    async def test_wrong_token_type_rejected(self, db: AsyncSession, client: AsyncClient):
        """Email verification token cannot be used for password reset."""
        user = await _create_user(db)
        await db.commit()

        # Create a verification token, not a reset token
        token = _make_token(str(user.id), "email_verification")

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpassword123"},
        )
        assert resp.status_code == 400

    async def test_token_for_deleted_user_returns_400(self, db: AsyncSession, client: AsyncClient):
        """Token with a non-existent user_id is rejected."""
        fake_id = str(uuid.uuid4())
        token = _make_token(fake_id, "password_reset")

        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpassword123"},
        )
        assert resp.status_code == 400

    async def test_password_too_short_returns_422(self, client: AsyncClient):
        """Password shorter than 8 chars is rejected by schema validation."""
        resp = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": "any-token", "new_password": "short"},
        )
        assert resp.status_code == 422

    async def test_token_reusable_since_jwt_based(self, db: AsyncSession, client: AsyncClient):
        """JWT-based tokens are stateless — same token works twice within expiry.
        This is a known trade-off of JWT tokens vs DB-stored tokens."""
        user = await _create_user(db, password="oldpassword123")
        await db.commit()

        token = _make_token(str(user.id), "password_reset")

        # First use
        resp1 = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpass111111"},
        )
        assert resp1.status_code == 200

        # Second use (still valid since JWT hasn't expired)
        resp2 = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "newpass222222"},
        )
        assert resp2.status_code == 200

    async def test_reset_then_login_with_new_password(self, db: AsyncSession, client: AsyncClient):
        """After reset, user can log in with new password."""
        email = f"login-after-reset-{uuid.uuid4().hex[:8]}@test.com"
        user = await _create_user(db, email=email, password="oldpassword123")
        await db.commit()

        token = _make_token(str(user.id), "password_reset")
        await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": "brandnewpass123"},
        )

        # Login with new password
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "brandnewpass123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()


# ── Email Verification ──────────────────────────────────────────────


@pytest.mark.asyncio
class TestEmailVerification:
    async def test_verify_valid_token(self, db: AsyncSession, client: AsyncClient):
        """Valid verification token sets email_verified_at."""
        user = await _create_user(db)
        await db.commit()

        assert user.email_verified_at is None

        token = _make_token(str(user.id), "email_verification", timedelta(hours=24))

        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": token},
        )
        assert resp.status_code == 200
        assert "verified" in resp.json()["message"].lower()

        await db.refresh(user)
        assert user.email_verified_at is not None

    async def test_verify_expired_token_returns_400(self, db: AsyncSession, client: AsyncClient):
        """Expired verification token is rejected."""
        user = await _create_user(db)
        await db.commit()

        token = _make_expired_token(str(user.id), "email_verification")

        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": token},
        )
        assert resp.status_code == 400

    async def test_verify_already_verified_is_idempotent(self, db: AsyncSession, client: AsyncClient):
        """Re-verifying already-verified email returns 200 (idempotent)."""
        user = await _create_user(db)
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()

        token = _make_token(str(user.id), "email_verification", timedelta(hours=24))

        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": token},
        )
        assert resp.status_code == 200

    async def test_verify_invalid_token_returns_400(self, client: AsyncClient):
        """Invalid token is rejected."""
        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": "garbage-token"},
        )
        assert resp.status_code == 400

    async def test_reset_token_cannot_verify_email(self, db: AsyncSession, client: AsyncClient):
        """Password reset token type cannot be used for email verification."""
        user = await _create_user(db)
        await db.commit()

        token = _make_token(str(user.id), "password_reset")

        resp = await client.post(
            "/api/v1/auth/verify-email",
            json={"token": token},
        )
        assert resp.status_code == 400


# ── Send Verification ───────────────────────────────────────────────


@pytest.mark.asyncio
class TestSendVerification:
    async def test_send_verification_to_unverified_user(self, client: AsyncClient):
        """Authenticated unverified user can request verification email."""
        headers = await auth_headers(client)
        resp = await client.post("/api/v1/auth/send-verification", headers=headers)
        assert resp.status_code == 200
        assert "sent" in resp.json()["message"].lower()

    async def test_send_verification_already_verified_returns_400(
        self, client: AsyncClient, db: AsyncSession
    ):
        """Already-verified user gets 400."""
        email = f"verified-{uuid.uuid4().hex[:8]}@test.com"
        headers = await auth_headers(client, email)

        # Mark user as verified
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one()
        user.email_verified_at = datetime.now(timezone.utc)
        await db.commit()

        resp = await client.post("/api/v1/auth/send-verification", headers=headers)
        assert resp.status_code == 400

    async def test_send_verification_unauthenticated_returns_401(self, client: AsyncClient):
        """Unauthenticated request is rejected."""
        resp = await client.post("/api/v1/auth/send-verification")
        assert resp.status_code in (401, 422)
