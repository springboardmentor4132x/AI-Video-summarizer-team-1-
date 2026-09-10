from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional
from enum import Enum
from uuid import UUID

class SummaryStatusEnum(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Request Schemas
class SummaryCreate(BaseModel):
    transcript_id: UUID

class SummaryUpdate(BaseModel):
    short_summary: Optional[str] = None
    detailed_summary: Optional[str] = None
    status: Optional[SummaryStatusEnum] = None

# Response Schemas
class SummaryResponse(BaseModel):
    id: UUID
    transcript_id: UUID
    short_summary: Optional[str] = None
    detailed_summary: Optional[str] = None
    status: SummaryStatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class SummaryWithTranscriptResponse(SummaryResponse):
    transcript_text: Optional[str] = None
    video_id: Optional[UUID] = None
    