import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError, ConflictError, NotFoundError, UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.user import TokenPair, UserRegister
from app.services import email_service


async def register_user(db: AsyncSession, data: UserRegister) -> User:
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise ConflictError("Email already registered")

    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)
    await db.flush()
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> TokenPair:
    from app.core.login_lockout import check_lockout, clear_attempts, record_failed_attempt

    await check_lockout(email)

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        await record_failed_attempt(email)
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise UnauthorizedError("Account is deactivated")

    await clear_attempts(email)

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def refresh_tokens(db: AsyncSession, refresh_token: str) -> TokenPair:
    payload = decode_token(refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def change_password(
    db: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    if not verify_password(current_password, user.password_hash):
        raise BadRequestError("Current password is incorrect")
    user.password_hash = hash_password(new_password)


async def update_user(db: AsyncSession, user: User, full_name: str | None) -> User:
    if full_name is not None:
        user.full_name = full_name
    await db.flush()
    return user


def _create_email_token(subject: str, purpose: str, expires_delta: timedelta) -> str:
    """Create a short-lived JWT for password reset or email verification."""
    from jose import jwt
    from app.config import settings

    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "type": purpose, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _decode_email_token(token: str, expected_type: str) -> str | None:
    """Decode and validate an email token. Returns the subject (user_id) or None."""
    payload = decode_token(token)
    if payload is None or payload.get("type") != expected_type:
        return None
    return payload.get("sub")


# --- Password Reset ---


async def request_password_reset(db: AsyncSession, email: str) -> None:
    """Generate a password reset token and send a reset email.

    Always returns successfully to prevent email enumeration.
    """
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None:
        return  # Silent — don't reveal whether email exists

    token = _create_email_token(
        subject=str(user.id),
        purpose="password_reset",
        expires_delta=timedelta(hours=1),
    )
    await email_service.send_password_reset_email(to=user.email, token=token)


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    """Validate reset token and set new password."""
    user_id = _decode_email_token(token, "password_reset")
    if user_id is None:
        raise BadRequestError("Invalid or expired reset token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise BadRequestError("Invalid or expired reset token")

    user.password_hash = hash_password(new_password)
    await db.flush()


# --- Email Verification ---


async def send_verification(db: AsyncSession, user: User) -> None:
    """Send a verification email to the current user."""
    if user.email_verified_at is not None:
        raise BadRequestError("Email is already verified")

    token = _create_email_token(
        subject=str(user.id),
        purpose="email_verification",
        expires_delta=timedelta(hours=24),
    )
    await email_service.send_verification_email(to=user.email, token=token)


async def verify_email(db: AsyncSession, token: str) -> None:
    """Validate verification token and mark email as verified."""
    user_id = _decode_email_token(token, "email_verification")
    if user_id is None:
        raise BadRequestError("Invalid or expired verification token")

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id)))
    user = result.scalar_one_or_none()
    if user is None:
        raise BadRequestError("Invalid or expired verification token")

    if user.email_verified_at is not None:
        return  # Already verified — idempotent

    user.email_verified_at = datetime.now(timezone.utc)
    await db.flush()
