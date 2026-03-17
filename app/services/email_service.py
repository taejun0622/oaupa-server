"""Fake email service — logs emails to console/file. Swap for a real provider later."""

import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

_EMAIL_LOG_DIR = Path("logs/emails")


async def send_email(
    to: str,
    subject: str,
    body: str,
    template: str | None = None,
) -> None:
    """Send an email (currently logs to console and optionally to file).

    Parameters
    ----------
    to: recipient email address
    subject: email subject line
    body: plain-text or HTML body
    template: optional template name for future provider integration
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = (
        f"\n{'=' * 60}\n"
        f"EMAIL SENT at {timestamp}\n"
        f"To: {to}\n"
        f"Subject: {subject}\n"
        f"Template: {template or 'none'}\n"
        f"{'─' * 60}\n"
        f"{body}\n"
        f"{'=' * 60}\n"
    )

    logger.info(log_entry)

    # Also write to file for easy inspection during development
    try:
        _EMAIL_LOG_DIR.mkdir(parents=True, exist_ok=True)
        log_file = _EMAIL_LOG_DIR / "sent.log"
        with open(log_file, "a") as f:
            f.write(log_entry)
    except OSError:
        pass  # File logging is best-effort


async def send_password_reset_email(to: str, token: str) -> None:
    reset_url = f"{settings.cors_origins[0]}/reset-password?token={token}"
    await send_email(
        to=to,
        subject="Reset your OAUPA password",
        body=(
            f"You requested a password reset.\n\n"
            f"Click the link below to reset your password:\n"
            f"{reset_url}\n\n"
            f"This link expires in 1 hour.\n"
            f"If you didn't request this, you can safely ignore this email."
        ),
        template="password_reset",
    )


async def send_verification_email(to: str, token: str) -> None:
    verify_url = f"{settings.cors_origins[0]}/verify-email?token={token}"
    await send_email(
        to=to,
        subject="Verify your OAUPA email address",
        body=(
            f"Welcome to OAUPA!\n\n"
            f"Click the link below to verify your email address:\n"
            f"{verify_url}\n\n"
            f"This link expires in 24 hours."
        ),
        template="email_verification",
    )
