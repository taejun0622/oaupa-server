import logging
import warnings

from pydantic import model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_INSECURE_JWT_DEFAULTS = {"change-me-in-production", ""}


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # App
    environment: str = "dev"
    app_name: str = "oaupa"
    debug: bool = False

    # Database — set DATABASE_URL directly, or use individual DB_* vars
    database_url: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "oaupa"
    db_password: str = "oaupa"
    db_name: str = "oaupa"

    @property
    def sync_database_url(self) -> str:
        return self.database_url.replace("+asyncpg", "+psycopg2")

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Security
    oaupa_master_key: str = ""
    jwt_secret_key: str = "change-me-in-production"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    jwt_algorithm: str = "HS256"

    # OAuth
    oauth_callback_base_url: str = "http://localhost:8000/api/v1/oauth/callback"

    # Stripe
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_free: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""

    # AWS SES
    ses_region: str = "us-east-1"
    ses_from_email: str = ""

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_allow_methods: list[str] = ["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"]
    cors_allow_headers: list[str] = ["Authorization", "Content-Type"]

    @model_validator(mode="after")
    def validate_config(self) -> "Settings":
        # Resolve database URL: DATABASE_URL > DB_HOST (if full URL) > individual parts
        url = self.database_url
        if not url and self.db_host.startswith("postgresql"):
            url = self.db_host
        if url:
            if not url.startswith("postgresql+asyncpg://"):
                url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
            self.database_url = url
        else:
            self.database_url = (
                f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}"
            )

        is_prod = self.environment == "production"

        # JWT secret must be changed in production
        if self.jwt_secret_key in _INSECURE_JWT_DEFAULTS:
            if is_prod:
                raise ValueError(
                    "JWT_SECRET_KEY must be set to a secure random value in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
                )
            warnings.warn(
                "JWT_SECRET_KEY is using an insecure default. "
                "Set JWT_SECRET_KEY to a secure random value before deploying.",
                stacklevel=2,
            )

        # Master encryption key is required in production
        if is_prod and not self.oaupa_master_key:
            raise ValueError(
                "OAUPA_MASTER_KEY must be set in production. "
                "Generate one with: python scripts/generate_encryption_key.py"
            )

        # Stripe keys required in production
        if is_prod:
            missing_stripe = []
            if not self.stripe_secret_key:
                missing_stripe.append("STRIPE_SECRET_KEY")
            if not self.stripe_publishable_key:
                missing_stripe.append("STRIPE_PUBLISHABLE_KEY")
            if not self.stripe_webhook_secret:
                missing_stripe.append("STRIPE_WEBHOOK_SECRET")
            if missing_stripe:
                raise ValueError(
                    f"Missing required Stripe config in production: {', '.join(missing_stripe)}"
                )
        elif not self.stripe_secret_key:
            logger.info("Stripe keys not configured — billing features will be unavailable")

        return self


settings = Settings()
