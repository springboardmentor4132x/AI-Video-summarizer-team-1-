from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum

class TranscriptStatusEnum(str, Enum):
    PENDING = "PENDING"
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Request Schemas
class TranscriptCreate(BaseModel):
    video_id: int
    language: Optional[str] = "en"

class TranscriptUpdate(BaseModel):
    text: Optional[str] = None
    language: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None
    status: Optional[TranscriptStatusEnum] = None

# Response Schemas
class TranscriptResponse(BaseModel):
    id: int
    video_id: int
    text: Optional[str] = None
    language: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None
    status: TranscriptStatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class TranscriptWithVideoResponse(TranscriptResponse):
    video_title: Optional[str] = None
    video_filename: Optional[str] = None