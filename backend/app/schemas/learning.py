from datetime import datetime
from pydantic import BaseModel, Field


class HistoryUpdate(BaseModel):
    position_seconds: int = Field(default=0, ge=0)
    watched_seconds: int = Field(default=0, ge=0, le=30)


class BookmarkCreate(BaseModel):
    video_id: int = Field(ge=1)
    key_moment_id: int | None = Field(default=None, ge=1)
    kind: str = Field(default="summary", pattern="^(summary|highlight)$")
    note: str | None = Field(default=None, max_length=1000)


class MaterialCreate(BaseModel):
    video_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)


class ShareCreate(BaseModel):
    video_id: int = Field(ge=1)
    audience: str = Field(default="students", min_length=1, max_length=200)


class ClassroomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)


class ClassroomJoin(BaseModel):
    invite_code: str = Field(min_length=6, max_length=40)


class ClassroomResourceCreate(BaseModel):
    resource_type: str = Field(pattern="^(video|material)$")
    resource_id: int = Field(ge=1)
