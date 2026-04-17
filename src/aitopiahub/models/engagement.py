import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from aitopiahub.core.database import Base


class EngagementMetric(Base):
    __tablename__ = "engagement_metrics"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    post_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("posts.id", ondelete="CASCADE"),
        nullable=False,
    )
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Instagram Insights metrikleri
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    reach: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    saves: Mapped[int] = mapped_column(Integer, default=0)
    profile_visits: Mapped[int] = mapped_column(Integer, default=0)

    # Hesaplanmış
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0)
    save_rate: Mapped[float] = mapped_column(Float, default=0.0)

    post: Mapped["Post"] = relationship(back_populates="metrics")  # noqa: F821


class ABTestResult(Base):
    __tablename__ = "ab_test_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    variant_group: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    winning_variant: Mapped[str | None] = mapped_column(String(1), nullable=True)
    metric_used: Mapped[str] = mapped_column(String(30), default="engagement_rate")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    concluded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
