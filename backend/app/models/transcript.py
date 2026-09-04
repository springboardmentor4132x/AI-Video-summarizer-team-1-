from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base
import enum

class TranscriptStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(Text, nullable=True)
    status = Column(Enum(TranscriptStatus), default=TranscriptStatus.NOT_STARTED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Foreign key to Video (one transcript per video)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, unique=True)
    
    # Relationships
    video = relationship("Video", back_populates="transcript")
    
