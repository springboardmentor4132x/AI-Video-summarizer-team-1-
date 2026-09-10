from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from uuid import UUID

class TranscriptStatusEnum(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

# Request Schemas
class TranscriptCreate(BaseModel):
    video_id: UUID
    language: Optional[str] = "en"

class TranscriptUpdate(BaseModel):
    text: Optional[str] = None
    language: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None
    status: Optional[TranscriptStatusEnum] = None

# Response Schemas
class TranscriptResponse(BaseModel):
    id: UUID
    video_id: UUID
    text: Optional[str] = None
    language: Optional[str] = None
    segments: Optional[List[Dict[str, Any]]] = None
    status: TranscriptStatusEnum
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = ConfigDict(from_attributes=True)

class TranscriptWithVideoResponse(TranscriptResponse):
    video_title: Optional[str] = None
    video_filename: Optional[str] = None