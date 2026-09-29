"""Authorized video upload history routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.authorization import Permission, require_permissions
from app.database import get_db
from app.models import UploadHistory, User, Video
from app.schemas.upload_history import UploadHistoryResponse


router = APIRouter(tags=["upload history"])


def _to_response(video: Video) -> UploadHistoryResponse:
    """Map the current video row and latest event metadata to the response."""

    latest_event = max(video.upload_history, key=lambda event: event.uploaded_at, default=None)
    return UploadHistoryResponse(
        id=latest_event.id if latest_event else video.id,
        video_id=video.id,
        filename=video.filename,
        owner_id=video.user_id,
        owner_name=video.owner.full_name,
        status=video.processing_status,
        timestamp=video.uploaded_at,
        notes=latest_event.notes if latest_event else None,
        mime_type=video.mime_type,
        file_size_bytes=video.file_size_bytes,
        duration_seconds=video.duration_seconds,
        source_type=video.source_type,
    )


def _history_query(limit: int):
    return (
        select(Video)
        .options(joinedload(Video.owner), joinedload(Video.upload_history))
        .order_by(Video.uploaded_at.desc())
        .limit(limit)
    )


@router.get("/videos/history", response_model=list[UploadHistoryResponse])
def creator_upload_history(
    user: User = Depends(require_permissions(Permission.VIEW_UPLOAD_HISTORY)),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[UploadHistoryResponse]:
    """Return upload events for videos owned by the authenticated creator."""

    videos = db.scalars(_history_query(limit).where(Video.user_id == user.id)).unique().all()
    return [_to_response(video) for video in videos]


@router.get("/admin/upload-history", response_model=list[UploadHistoryResponse])
def administrator_upload_history(
    user: User = Depends(require_permissions(Permission.MONITOR_PLATFORM_ACTIVITY)),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[UploadHistoryResponse]:
    """Return recent upload events across the platform for administrators."""

    videos = db.scalars(_history_query(limit)).unique().all()
    return [_to_response(video) for video in videos]
