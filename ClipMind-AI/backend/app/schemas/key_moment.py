"""Key moment API schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class KeyMomentResponse(BaseModel):
    id: UUID
    video_id: UUID
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    title: str
    topic: str | None = None
    description: str
    importance_score: float = Field(ge=0, le=1)
    transcript_text: str
    created_at: datetime

    model_config = {"from_attributes": True}
