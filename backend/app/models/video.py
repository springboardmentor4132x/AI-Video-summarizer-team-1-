from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db.session import Base

class Video(Base):
    __tablename__ = "videos"  # ✅ FIXED: double underscore

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="uploaded")
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())  # ✅ FIXED: timezone

    # Relationship to User (using back_populates for consistency)
    user = relationship("User", back_populates="videos")
    
    # Relationship to Transcript (one video → one transcript)
    transcript = relationship("Transcript", back_populates="video", uselist=False, cascade="all, delete-orphan")
