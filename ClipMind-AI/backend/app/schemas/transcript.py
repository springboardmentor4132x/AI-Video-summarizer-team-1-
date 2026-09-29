"""Transcript API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.models import TranscriptStatus


class TranscriptSegment(BaseModel):
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    text: str

    @model_validator(mode="after")
    def validate_time_range(self) -> "TranscriptSegment":
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be greater than start_time")
        return self


class TranscriptResponse(BaseModel):
    id: UUID
    video_id: UUID
    text: str
    segments: list[TranscriptSegment]
    language: str | None
    status: TranscriptStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class TranscriptUpdateRequest(BaseModel):
    text: str = Field(min_length=1)
    segments: list[TranscriptSegment] | None = None