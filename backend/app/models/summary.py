from sqlalchemy import Column, Text, DateTime, ForeignKey, Enum, Uuid
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uuid import uuid4
from app.db.session import Base
import enum

class SummaryStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class Summary(Base):
    __tablename__ = "summaries"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4, index=True)
    short_summary = Column(Text, nullable=True)
    detailed_summary = Column(Text, nullable=True)
    status = Column(Enum(SummaryStatus, name="summarystatus"), default=SummaryStatus.NOT_STARTED)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    transcript_id = Column(Uuid(as_uuid=True), ForeignKey("transcripts.id"), nullable=False, unique=True)
    
    transcript = relationship("Transcript", back_populates="summary")