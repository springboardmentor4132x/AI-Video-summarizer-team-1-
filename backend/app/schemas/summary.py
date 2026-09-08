from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from enum import Enum

class SummaryStatusEnum(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Request Schemas
class SummaryCreate(BaseModel):
    transcript_id: int

class SummaryUpdate(BaseModel):
    short_summary: Optional[str] = None
    detailed_summary: Optional[str] = None
    status: Optional[SummaryStatusEnum] = None

# Response Schemas
class SummaryResponse(BaseModel):
    id: int
    transcript_id: int
    short_summary: Optional[str] = None
    detailed_summary: Optional[str] = None
    status: SummaryStatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class SummaryWithTranscriptResponse(SummaryResponse):
    transcript_text: Optional[str] = None
    video_id: Optional[int] = None
    