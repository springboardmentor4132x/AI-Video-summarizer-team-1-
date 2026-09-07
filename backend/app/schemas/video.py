from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VideoResponse(BaseModel):
    id: int
    filename: str
    status: str
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VideoStatusResponse(BaseModel):
    id: int
    status: str

    model_config = ConfigDict(from_attributes=True)
