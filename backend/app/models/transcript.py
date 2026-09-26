import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    ForeignKey,
    Enum,
    JSON,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.session import Base


class TranscriptStatus(str, enum.Enum):
    PENDING = "PENDING"
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Transcript(Base):
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True, index=True)

    text = Column(Text, nullable=True)
    language = Column(String(10), nullable=True)
    segments = Column(JSON, nullable=True, default=list)
    status = Column(
        Enum(TranscriptStatus),
        default=TranscriptStatus.PENDING,
        nullable=False,
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at = Column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
    )

    video_id = Column(
        Integer,
        ForeignKey("videos.id"),
        nullable=False,
        unique=True,
    )

    video = relationship("Video", back_populates="transcript")
    
    summary = relationship(
        "Summary",
        back_populates="transcript",
        uselist=False,
        cascade="all, delete-orphan",
    )
