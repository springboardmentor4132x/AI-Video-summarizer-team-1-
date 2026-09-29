"""Upload history ORM model."""

from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.video import Video


class UploadStatus(StrEnum):
    """Statuses recorded during upload and processing lifecycle events."""

    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    VALIDATING = "VALIDATING"
    FFMPEG_PROCESSING = "FFMPEG_PROCESSING"
    READY_FOR_AI = "READY_FOR_AI"
    AI_PROCESSING = "AI_PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UploadHistory(Base):
    """An immutable-style status event for a video upload workflow."""

    __tablename__ = "upload_history"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    video_id: Mapped[UUID] = mapped_column(
        ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, name="upload_status"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False, index=True
    )

    video: Mapped["Video"] = relationship(back_populates="upload_history")

