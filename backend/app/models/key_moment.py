from sqlalchemy import Column, Float, String, Text, DateTime, ForeignKey, Uuid
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from uuid import uuid4

from app.db.session import Base


class KeyMoment(Base):
    __tablename__ = "key_moments"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid4, index=True)

    video_id = Column(
        Uuid(as_uuid=True),
        ForeignKey("videos.id"),
        nullable=False,
        index=True,
    )

    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)

    title = Column(String, nullable=False)
    topic = Column(String, nullable=True)

    importance_score = Column(Float, nullable=False)

    text = Column(Text, nullable=False)

    highlight_path = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    video = relationship("Video", back_populates="key_moments")