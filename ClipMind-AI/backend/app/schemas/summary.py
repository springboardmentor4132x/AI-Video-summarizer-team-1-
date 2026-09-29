"""Summary API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.models import SummaryStatus


class GeminiSummaryOutput(BaseModel):
    short_summary: str
    long_summary: str
    key_points: list[str]

    @model_validator(mode="after")
    def validate_summary_content(self) -> "GeminiSummaryOutput":
        if not self.short_summary.strip():
            raise ValueError("Short summary must not be empty.")
        if not self.long_summary.strip():
            raise ValueError("Long summary must not be empty.")
        if any(not point.strip() for point in self.key_points):
            raise ValueError("Key points must contain non-empty text.")
        return self


class SummaryResponse(BaseModel):
    id: UUID
    video_id: UUID
    content: str
    overview: str
    main_points: list[str]
    key_takeaways: list[str]
    duration_seconds: int | None
    status: SummaryStatus
    error_message: str | None
    created_at: datetime
    updated_at: datetime
