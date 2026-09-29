"""Video upload response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator

from app.models import VideoProcessingStatus, VideoSourceType


class VideoStatusUpdateRequest(BaseModel):
    """Requested lifecycle transition for a video."""

    status: VideoProcessingStatus
    notes: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, value: str | VideoProcessingStatus) -> VideoProcessingStatus:
        return VideoProcessingStatus(str(value).upper())


class VideoUploadResponse(BaseModel):
    """Metadata returned after a video is accepted for processing."""

    id: UUID
    filename: str
    mime_type: str
    file_size_bytes: int
    processing_status: str
    source_type: VideoSourceType = VideoSourceType.UPLOAD
    source_url: str | None = None
    uploaded_at: datetime


class VideoStatusResponse(BaseModel):
    """Current processing state returned to an authorized user."""

    id: UUID
    filename: str
    processing_status: VideoProcessingStatus
    updated_at: datetime
    latest_note: str | None = None


class VideoListResponse(BaseModel):
    """Safe video metadata for authorized library views."""

    id: UUID
    filename: str
    mime_type: str
    file_size_bytes: int
    duration_seconds: int | None
    processing_status: VideoProcessingStatus
    source_type: VideoSourceType = VideoSourceType.UPLOAD
    source_url: str | None = None
    uploaded_at: datetime
    owner_id: int
    owner_name: str


class YouTubeVideoRequest(BaseModel):
    """Request body for creating a YouTube-backed video record."""

    youtube_url: str

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("YouTube URL is required")
        return cleaned


class YouTubeVideoResponse(BaseModel):
    """Metadata returned after accepting a YouTube source for processing."""

    video_id: UUID
    source_type: VideoSourceType = VideoSourceType.YOUTUBE
    source_url: str
    status: VideoProcessingStatus = VideoProcessingStatus.PROCESSING
