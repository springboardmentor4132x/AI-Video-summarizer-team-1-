"""Admin-only endpoints for the ClipMind AI platform."""

from pathlib import Path
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.dependencies.auth import require_role
from app.models.key_moment import KeyMoment
from app.models.summary import Summary
from app.models.transcript import Transcript
from app.models.user import User
from app.models.video import Video
from app.models.learning import AuditLog
from app.schemas.admin import (
    AdminContentResponse,
    AdminProcessingResponse,
    AdminRoleUpdate,
    AdminStorageResponse,
    AdminUserResponse,
)
from app.schemas.user import UserRole
from app.schemas.video import VideoResponse
from app.schemas.analytics import AnalyticsDashboard
from app.services.analytics import build_dashboard


router = APIRouter(
    prefix="/admin",
    tags=["admin"],
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = (BACKEND_DIR / "uploads").resolve()


def _admin_user(current_user=Depends(require_role(UserRole.ADMINISTRATOR))):
    return current_user


@router.get(
    "/upload-history",
    response_model=list[VideoResponse],
    dependencies=[Depends(require_role(UserRole.ADMINISTRATOR))],
)
def get_admin_upload_history(
    db: Session = Depends(get_db),
):
    """Return upload history for all users on the platform.

    Accessible by Administrators only.  Results are ordered most-recent first,
    matching the ordering used by the per-user ``/videos/history`` endpoint.
    """
    return (
        db.query(Video)
        .order_by(Video.uploaded_at.desc())
        .all()
    )


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(
    _: User = Depends(_admin_user),
    db: Session = Depends(get_db),
    role: UserRole | None = Query(default=None),
):
    query = db.query(User).order_by(User.created_at.desc())
    if role is not None:
        query = query.filter(User.role == role.value.lower())
    return query.all()


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
def update_user_role(
    user_id: int,
    payload: AdminRoleUpdate,
    current_user: User = Depends(_admin_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=403, detail="Administrators cannot change their own role")
    previous_role = user.role
    user.role = payload.role.value.lower()
    db.add(AuditLog(actor_id=current_user.id, action="admin.user.role_change", resource=f"user:{user.id}:{previous_role}->{user.role}"))
    db.commit()
    db.refresh(user)
    return user


@router.get("/content", response_model=list[AdminContentResponse])
def list_content(
    _: User = Depends(_admin_user),
    db: Session = Depends(get_db),
    owner_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status"),
):
    query = db.query(Video).options(joinedload(Video.user)).order_by(Video.uploaded_at.desc())
    if owner_id is not None:
        query = query.filter(Video.user_id == owner_id)
    if status_filter:
        query = query.filter(Video.status == status_filter)
    return [
        AdminContentResponse(
            id=video.id,
            filename=video.filename,
            status=video.status,
            user_id=video.user_id,
            owner_name=video.user.name,
            owner_email=video.user.email,
            uploaded_at=video.uploaded_at,
            processing_stage=video.processing_stage,
            processing_error_code=video.processing_error_code,
            processing_started_at=video.processing_started_at,
            processing_completed_at=video.processing_completed_at,
            duration_seconds=video.duration_seconds,
        )
        for video in query.all()
    ]


@router.delete("/content/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_content(
    video_id: int,
    current_user: User = Depends(_admin_user),
    db: Session = Depends(get_db),
):
    video = db.query(Video).options(joinedload(Video.key_moments)).filter(Video.id == video_id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    paths = [Path(video.file_path)]
    paths.extend(Path(moment.highlight_path) for moment in video.key_moments if moment.highlight_path)
    db.add(AuditLog(actor_id=current_user.id, action="admin.content.delete", resource=f"video:{video.id}"))
    db.delete(video)
    db.commit()
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


@router.get("/processing", response_model=list[AdminProcessingResponse])
def list_processing_jobs(
    _: User = Depends(_admin_user),
    db: Session = Depends(get_db),
):
    videos = db.query(Video).options(joinedload(Video.user)).order_by(Video.uploaded_at.desc()).all()
    jobs = []
    for video in videos:
        transcript = video.transcript
        summary = transcript.summary if transcript else None
        jobs.append(
            AdminProcessingResponse(
                video_id=video.id,
                filename=video.filename,
                owner_id=video.user_id,
                owner_name=video.user.name,
                video_status=video.status,
                video_stage=video.processing_stage,
                video_started_at=video.processing_started_at,
                video_completed_at=video.processing_completed_at,
                video_duration_seconds=video.duration_seconds,
                video_error_code=video.processing_error_code,
                video_error_message=video.processing_error_message,
                transcript_status=transcript.status.value if transcript else None,
                transcript_started_at=transcript.processing_started_at if transcript else None,
                transcript_completed_at=transcript.processing_completed_at if transcript else None,
                transcript_duration_seconds=transcript.processing_duration_seconds if transcript else None,
                transcript_error_code=transcript.error_code if transcript else None,
                transcript_error_message=transcript.error_message if transcript else None,
                summary_status=summary.status.value if summary else None,
                summary_started_at=summary.processing_started_at if summary else None,
                summary_completed_at=summary.processing_completed_at if summary else None,
                summary_duration_seconds=summary.processing_duration_seconds if summary else None,
                summary_error_code=summary.error_code if summary else None,
                summary_error_message=summary.error_message if summary else None,
            )
        )
    return jobs


@router.get("/storage", response_model=AdminStorageResponse)
def get_storage_usage(_: User = Depends(_admin_user), db: Session = Depends(get_db)):
    videos = db.query(Video).all()
    moments = db.query(KeyMoment).filter(KeyMoment.highlight_path.is_not(None)).all()
    video_files = [Path(video.file_path) for video in videos if video.file_path]
    highlight_files = [Path(moment.highlight_path) for moment in moments if moment.highlight_path]
    existing = [path for path in video_files + highlight_files if path.is_file()]
    return AdminStorageResponse(
        upload_root=str(UPLOAD_DIR),
        total_bytes=sum(path.stat().st_size for path in existing),
        video_file_count=sum(path.is_file() for path in video_files),
        highlight_file_count=sum(path.is_file() for path in highlight_files),
        missing_video_files=sum(not path.is_file() for path in video_files),
        missing_highlight_files=sum(not path.is_file() for path in highlight_files),
    )


@router.get("/activity", response_model=list[AdminContentResponse])
def get_platform_activity(
    _: User = Depends(_admin_user),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return recent content activity derived from current platform records."""
    videos = (
        db.query(Video)
        .options(joinedload(Video.user))
        .order_by(Video.uploaded_at.desc())
        .limit(limit)
        .all()
    )
    return [
        AdminContentResponse(
            id=video.id,
            filename=video.filename,
            status=video.status,
            user_id=video.user_id,
            owner_name=video.user.name,
            owner_email=video.user.email,
            uploaded_at=video.uploaded_at,
            processing_stage=video.processing_stage,
            processing_error_code=video.processing_error_code,
            processing_started_at=video.processing_started_at,
            processing_completed_at=video.processing_completed_at,
            duration_seconds=video.duration_seconds,
        )
        for video in videos
    ]


@router.get("/reports", response_model=AnalyticsDashboard)
def get_admin_reports(
    _: User = Depends(_admin_user),
    db: Session = Depends(get_db),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="The 'from' date must not be after the 'to' date")
    return build_dashboard(db, date_from=date_from, date_to=date_to)
