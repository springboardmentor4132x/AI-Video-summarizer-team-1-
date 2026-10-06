"""Analytics router providing owner-scoped and platform-wide analytics."""

from datetime import date, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_role
from app.models.user import User
from app.models.learning import LearningHistory
from app.models.video import Video
from app.schemas.analytics import AnalyticsDashboard, CreatorEngagement, CreatorEngagementVideo
from app.schemas.user import UserRole
from app.services.analytics import build_dashboard

router = APIRouter(tags=["analytics"])


@router.get("/admin/analytics", response_model=AnalyticsDashboard)
def get_admin_analytics(
    current_user: User = Depends(require_role(UserRole.ADMINISTRATOR)),
    db: Session = Depends(get_db),
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
) -> AnalyticsDashboard:
    """Return platform-wide aggregate analytics. Accessible only by Administrators."""
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The 'from' date must not be after the 'to' date",
        )
    return build_dashboard(db, date_from=date_from, date_to=date_to)


@router.get("/analytics", response_model=AnalyticsDashboard)
def get_creator_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    date_from: Optional[date] = Query(default=None, alias="from"),
    date_to: Optional[date] = Query(default=None, alias="to"),
) -> AnalyticsDashboard:
    """Return owner-scoped analytics limited to the authenticated creator's videos."""
    user_role_normalized = current_user.role.title() if isinstance(current_user.role, str) else current_user.role
    if user_role_normalized not in ("Content Creator", "Educator", "Administrator"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only content creators, educators, or administrators can access analytics",
        )
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The 'from' date must not be after the 'to' date",
        )
    # If Administrator calls /analytics without /admin, or Content Creator calls it:
    # Scope to current_user.id for Content Creator
    user_id = current_user.id if user_role_normalized != "Administrator" else None
    dashboard = build_dashboard(db, user_id=user_id, date_from=date_from, date_to=date_to)
    if user_id is None:
        return dashboard

    videos = db.query(Video).filter(Video.user_id == user_id).all()
    video_ids = [video.id for video in videos]
    history_query = db.query(LearningHistory).filter(LearningHistory.video_id.in_(video_ids))
    if date_from:
        history_query = history_query.filter(LearningHistory.viewed_at >= datetime.combine(date_from, time.min))
    if date_to:
        history_query = history_query.filter(LearningHistory.viewed_at < datetime.combine(date_to + timedelta(days=1), time.min))
    history = history_query.all() if video_ids else []
    dashboard.learner_engagement = CreatorEngagement(
        learner_records=len(history),
        unique_learners=len({row.user_id for row in history}),
        watch_time_seconds=sum(row.watch_duration_seconds or 0 for row in history),
        average_completion_percentage=(
            round(sum(row.completion_percentage or 0 for row in history) / len(history), 2)
            if history else None
        ),
        by_video=[
            CreatorEngagementVideo(
                video_id=video.id,
                filename=video.filename,
                learner_records=sum(1 for row in history if row.video_id == video.id),
                unique_learners=len({row.user_id for row in history if row.video_id == video.id}),
                watch_time_seconds=sum(row.watch_duration_seconds or 0 for row in history if row.video_id == video.id),
                average_completion_percentage=(
                    round(sum(row.completion_percentage or 0 for row in history if row.video_id == video.id)
                          / sum(1 for row in history if row.video_id == video.id), 2)
                    if any(row.video_id == video.id for row in history) else None
                ),
            ) for video in videos
        ],
    )
    return dashboard
