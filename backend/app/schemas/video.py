from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    file_size_bytes: int
    processing_status: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoStatusResponse(BaseModel):
    id: UUID
    processing_status: str

    model_config = ConfigDict(from_attributes=True)
