from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: datetime
    file_size_bytes: int = 0
    duration_seconds: int | None = None
    model_config = ConfigDict(from_attributes=True)


class VideoStatusResponse(BaseModel):
    id: int
    status: str

    model_config = ConfigDict(from_attributes=True)
