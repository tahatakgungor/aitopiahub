import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from aitopiahub.core.database import Base


class ContentDraft(Base):
    __tablename__ = "content_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    trend_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("trends.id", ondelete="SET NULL"),
        nullable=True,
    )

    # A/B test grubu
    variant_group: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    variant_label: Mapped[str | None] = mapped_column(String(1), nullable=True)  # 'A' veya 'B'

    # İçerik
    post_format: Mapped[str] = mapped_column(String(20), default="single")
    language: Mapped[str] = mapped_column(String(5), default="tr")
    caption_text: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    slide_texts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Ajan pipeline çıktıları
    researcher_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    writer_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    editor_output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Kalite metrikleri
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Durum
    status: Mapped[str] = mapped_column(String(20), default="draft")
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trend: Mapped["Trend"] = relationship(back_populates="drafts")  # noqa: F821
    images: Mapped[list["GeneratedImage"]] = relationship(back_populates="draft", cascade="all, delete-orphan")
    post: Mapped["Post | None"] = relationship(back_populates="draft", uselist=False)


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    template_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    prompt_used: Mapped[str | None] = mapped_column(Text, nullable=True)
    slide_index: Mapped[int] = mapped_column(Integer, default=0)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    draft: Mapped["ContentDraft"] = relationship(back_populates="images")


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("content_drafts.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    instagram_media_id: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    post_format: Mapped[str] = mapped_column(String(20), nullable=False)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_log: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    draft: Mapped["ContentDraft"] = relationship(back_populates="post")
    account: Mapped["Account"] = relationship(back_populates="posts")  # noqa: F821
    metrics: Mapped[list["EngagementMetric"]] = relationship(back_populates="post", cascade="all, delete-orphan")  # noqa: F821
