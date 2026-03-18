"""Email service using AWS SES."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

from app.config import settings

logger = logging.getLogger(__name__)

_EMAIL_LOG_DIR = Path("logs/emails")

_ses_client = boto3.client("ses", region_name=settings.ses_region)


def _log_email(to: str, subject: str, body: str, template: str | None) -> None:
    """Log email to console and file for debugging."""
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
    try:
        _EMAIL_LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_EMAIL_LOG_DIR / "sent.log", "a") as f:
            f.write(log_entry)
    except OSError:
        pass


async def send_email(
    to: str,
    subject: str,
    body: str,
    template: str | None = None,
) -> None:
    """Send an email via AWS SES.

    In dev mode (no ses_from_email configured), falls back to logging only.
    """
    _log_email(to, subject, body, template)

    if not settings.ses_from_email or settings.environment in ("test", "dev"):
        logger.warning("SES skipped (env=%s) — email logged but not sent", settings.environment)
        return

    try:
        _ses_client.send_email(
            Source=settings.ses_from_email,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": body, "Charset": "UTF-8"},
                },
            },
        )
        logger.info("SES email sent to %s (subject: %s)", to, subject)
    except ClientError:
        logger.exception("Failed to send email via SES to %s", to)
        raise


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
