from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db.session import Base
from app.models.key_moment import KeyMoment


class LearningHistory(Base):
    __tablename__ = "learning_history"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    last_position_seconds = Column(Integer, nullable=False, default=0)
    watch_duration_seconds = Column(Integer, nullable=False, default=0)
    completion_percentage = Column(Float, nullable=False, default=0.0)
    viewed_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    video = relationship("Video")
    __table_args__ = (UniqueConstraint("user_id", "video_id", name="uq_learning_history_user_video"),)


class LearningBookmark(Base):
    __tablename__ = "learning_bookmarks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    key_moment_id = Column(Integer, ForeignKey("key_moments.id", ondelete="CASCADE"), nullable=True)
    kind = Column(String(20), nullable=False, default="summary")
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    video = relationship("Video")
    key_moment = relationship("KeyMoment")
    __table_args__ = (
        UniqueConstraint("user_id", "video_id", "key_moment_id", "kind", name="uq_learning_bookmark"),
    )


class LearningMaterial(Base):
    __tablename__ = "learning_materials"
    id = Column(Integer, primary_key=True)
    educator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    video = relationship("Video")


class SharedSummary(Base):
    __tablename__ = "shared_summaries"
    id = Column(Integer, primary_key=True)
    educator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    audience = Column(String(200), nullable=False, default="students")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    video = relationship("Video")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    resource = Column(String(200), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    actor = relationship("User")


class PlatformSetting(Base):
    __tablename__ = "platform_settings"
    id = Column(Integer, primary_key=True)
    key = Column(String(100), nullable=False, unique=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    educator_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    invite_code = Column(String(40), nullable=False, unique=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ClassroomMember(Base):
    __tablename__ = "classroom_members"
    id = Column(Integer, primary_key=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    learner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("classroom_id", "learner_id", name="uq_classroom_member"),)


class ClassroomResource(Base):
    __tablename__ = "classroom_resources"
    id = Column(Integer, primary_key=True)
    classroom_id = Column(Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False, index=True)
    resource_type = Column(String(20), nullable=False)
    resource_id = Column(Integer, nullable=False)
    shared_by = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint("classroom_id", "resource_type", "resource_id", name="uq_classroom_resource"),)
