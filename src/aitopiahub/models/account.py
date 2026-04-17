import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from aitopiahub.core.database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    handle: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    niche: Mapped[str] = mapped_column(String(50), nullable=False)
    language_primary: Mapped[str] = mapped_column(String(5), default="tr")
    language_secondary: Mapped[str | None] = mapped_column(String(5), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Europe/Istanbul")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    posting_frequency_per_day: Mapped[int] = mapped_column(Integer, default=8)
    instagram_business_account_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    config_override: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    credentials: Mapped[list["AccountCredential"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    feed_sources: Mapped[list["FeedSource"]] = relationship(back_populates="account")  # noqa: F821
    trends: Mapped[list["Trend"]] = relationship(back_populates="account")  # noqa: F821
    posts: Mapped[list["Post"]] = relationship(back_populates="account")  # noqa: F821


class AccountCredential(Base):
    __tablename__ = "account_credentials"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_type: Mapped[str] = mapped_column(String(50), nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    account: Mapped["Account"] = relationship(back_populates="credentials")
