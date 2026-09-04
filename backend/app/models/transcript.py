import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db.session import Base


class TranscriptStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=True)
    language = Column(String, nullable=True)
    status = Column(Enum(TranscriptStatus), default=TranscriptStatus.NOT_STARTED)
    segments = Column(JSON, nullable=True, default=list)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, unique=True)

    video = relationship("Video", back_populates="transcript")
    summary = relationship("Summary", back_populates="transcript", uselist=False, cascade="all, delete-orphan")


class SummaryStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True, index=True)
    short_summary = Column(Text, nullable=True)
    detailed_summary = Column(Text, nullable=True)
    status = Column(Enum(SummaryStatus), default=SummaryStatus.NOT_STARTED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    transcript_id = Column(Integer, ForeignKey("transcripts.id"), nullable=False, unique=True)

    transcript = relationship("Transcript", back_populates="summary")
