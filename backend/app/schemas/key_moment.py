from pydantic import BaseModel, ConfigDict
from uuid import UUID


class KeyMomentResponse(BaseModel):
    id: UUID
    start_time: float
    end_time: float
    title: str
    topic: str | None = None
    importance_score: float
    text: str
    highlight_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class KeyMomentsResponse(BaseModel):
    video_id: UUID
    status: str
    key_moments: list[KeyMomentResponse]