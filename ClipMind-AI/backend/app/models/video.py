"""Video ORM model."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.key_moment import KeyMoment
    from app.models.summary import Summary
    from app.models.transcript import Transcript
    from app.models.upload_history import UploadHistory
    from app.models.user import User


class VideoProcessingStatus(StrEnum):
    """Supported Module 1 video processing states."""

    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    VALIDATING = "VALIDATING"
    FFMPEG_PROCESSING = "FFMPEG_PROCESSING"
    READY_FOR_AI = "READY_FOR_AI"
    AI_PROCESSING = "AI_PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VideoSourceType(StrEnum):
    """Supported video ingestion sources."""

    UPLOAD = "UPLOAD"
    YOUTUBE = "YOUTUBE"


class Video(Base):
    """Video metadata and cloud-storage reference."""

    __tablename__ = "videos"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_type: Mapped[VideoSourceType] = mapped_column(
        Enum(VideoSourceType, name="video_source_type"),
        default=VideoSourceType.UPLOAD,
        server_default="UPLOAD",
        nullable=False,
        index=True,
    )
    source_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    processing_status: Mapped[VideoProcessingStatus] = mapped_column(
        Enum(VideoProcessingStatus, name="video_processing_status"),
        default=VideoProcessingStatus.UPLOADING,
        nullable=False,
        index=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    owner: Mapped["User"] = relationship(back_populates="videos")
    upload_history: Mapped[list["UploadHistory"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="video", cascade="all, delete-orphan", uselist=False
    )
    summary: Mapped["Summary | None"] = relationship(
        back_populates="video", cascade="all, delete-orphan", uselist=False
    )
    key_moments: Mapped[list["KeyMoment"]] = relationship(
        back_populates="video", cascade="all, delete-orphan", order_by="KeyMoment.start_time"
    )

