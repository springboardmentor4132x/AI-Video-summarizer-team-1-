from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoStatusResponse(BaseModel):
    id: int
    status: str

    model_config = ConfigDict(from_attributes=True)


class OwnedVideoResponse(VideoResponse):
    """Video response for owner-scoped routes that need the owner identifier."""
    user_id: int


class VideoPipelineStatusResponse(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: datetime
    transcript_status: str
    summary_status: str
    key_moments_status: str
    key_moment_count: int
