import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TokenVault(Base):
    __tablename__ = "token_vault"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("oauth_connections.id"), unique=True, nullable=False, index=True
    )
    access_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    refresh_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    token_type: Mapped[str] = mapped_column(String(50), default="Bearer")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    raw_token_response_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_key_id: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    connection: Mapped["OAuthConnection"] = relationship(back_populates="token_vault")  # noqa: F821
