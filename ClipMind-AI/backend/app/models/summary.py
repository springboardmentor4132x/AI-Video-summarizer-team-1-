"""Summary ORM model."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if False:  # pragma: no cover
    from app.models.video import Video


class SummaryStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Summary(Base):
    """AI-generated summary associated to a single video."""

    __tablename__ = "summaries"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    transcript_id: Mapped[UUID] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    overview: Mapped[str] = mapped_column(Text, default="", nullable=False)
    main_points: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    key_takeaways: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[SummaryStatus] = mapped_column(
        Enum(SummaryStatus, name="summary_status"), default=SummaryStatus.COMPLETED, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    video: Mapped["Video"] = relationship(back_populates="summary")
