from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserRole


class AdminRoleUpdate(BaseModel):
    role: UserRole


class AdminUserResponse(BaseModel):
    id: int
    name: str
    email: str
    role: UserRole
    created_at: datetime

    @field_validator("role", mode="before")
    @classmethod
    def normalize_role(cls, value):
        return value.title() if isinstance(value, str) else value

    model_config = ConfigDict(from_attributes=True)


class AdminContentResponse(BaseModel):
    id: int
    filename: str
    status: str
    user_id: int
    owner_name: str
    owner_email: str
    uploaded_at: datetime
    processing_stage: str | None = None
    processing_error_code: str | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None
    duration_seconds: float | None = None


class AdminProcessingResponse(BaseModel):
    video_id: int
    filename: str
    owner_id: int
    owner_name: str
    video_status: str
    video_stage: str | None = None
    video_started_at: datetime | None = None
    video_completed_at: datetime | None = None
    video_duration_seconds: float | None = None
    video_error_code: str | None = None
    video_error_message: str | None = None
    transcript_status: str | None = None
    transcript_started_at: datetime | None = None
    transcript_completed_at: datetime | None = None
    transcript_duration_seconds: float | None = None
    transcript_error_code: str | None = None
    transcript_error_message: str | None = None
    summary_status: str | None = None
    summary_started_at: datetime | None = None
    summary_completed_at: datetime | None = None
    summary_duration_seconds: float | None = None
    summary_error_code: str | None = None
    summary_error_message: str | None = None


class AdminStorageResponse(BaseModel):
    upload_root: str
    total_bytes: int = Field(ge=0)
    video_file_count: int = Field(ge=0)
    highlight_file_count: int = Field(ge=0)
    missing_video_files: int = Field(ge=0)
    missing_highlight_files: int = Field(ge=0)


class TranscriptSearchMatch(BaseModel):
    video_id: int
    filename: str
    transcript_id: int
    status: str
    text: str
    start_time: float | None = None
    end_time: float | None = None


class TranscriptSearchResponse(BaseModel):
    query: str
    results: list[TranscriptSearchMatch]
