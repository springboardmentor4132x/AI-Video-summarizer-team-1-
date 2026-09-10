from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base

class Video(Base):
    __tablename__ = "videos"  # ✅ FIXED: double underscore

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    storage_key = Column(String(500), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    duration_seconds = Column(BigInteger, nullable=True)
    processing_status = Column(String(17), nullable=False, default="UPLOADED")
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationship to User (using back_populates for consistency)
    user = relationship("User", back_populates="videos")
    
    # Relationship to Transcript (one video → one transcript)
    transcript = relationship("Transcript", back_populates="video", uselist=False, cascade="all, delete-orphan")
    key_moments = relationship("KeyMoment",back_populates="video",cascade="all, delete-orphan")
