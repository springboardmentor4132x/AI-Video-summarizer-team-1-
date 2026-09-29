"""Upload history response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UploadHistoryResponse(BaseModel):
    """Current database-backed video status with its latest lifecycle note."""

    id: UUID
    video_id: UUID
    filename: str
    owner_id: int
    owner_name: str
    status: str
    timestamp: datetime
    notes: str | None
    mime_type: str
    file_size_bytes: int
    duration_seconds: int | None
    source_type: str
