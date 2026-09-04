from pydantic import BaseModel, ConfigDict


class KeyMomentResponse(BaseModel):
    id: int
    start_time: float
    end_time: float
    title: str
    topic: str | None = None
    importance_score: float
    text: str
    highlight_path: str | None = None

    model_config = ConfigDict(from_attributes=True)


class KeyMomentsResponse(BaseModel):
    video_id: int
    status: str
    key_moments: list[KeyMomentResponse]