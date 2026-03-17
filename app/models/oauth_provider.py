from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OAuthProvider(Base):
    __tablename__ = "oauth_providers"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    token_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    revoke_url: Mapped[str | None] = mapped_column(String(1024))
    client_id: Mapped[str] = mapped_column(String(512), nullable=False)
    client_secret_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    default_scopes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extra_auth_params: Mapped[dict] = mapped_column(JSONB, default={})
    token_refresh_buffer_secs: Mapped[int] = mapped_column(Integer, default=300)
    supports_refresh: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    icon_url: Mapped[str | None] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
