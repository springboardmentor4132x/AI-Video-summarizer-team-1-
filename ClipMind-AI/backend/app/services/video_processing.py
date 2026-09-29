"""Video processing status transition logic."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import TranscriptStatus, UploadHistory, UploadStatus, Video, VideoProcessingStatus


ALLOWED_TRANSITIONS: dict[VideoProcessingStatus, frozenset[VideoProcessingStatus]] = {
    VideoProcessingStatus.UPLOADED: frozenset(
        {VideoProcessingStatus.PROCESSING, VideoProcessingStatus.FAILED}
    ),
    VideoProcessingStatus.PROCESSING: frozenset(
        {VideoProcessingStatus.COMPLETED, VideoProcessingStatus.FAILED}
    ),
    VideoProcessingStatus.FAILED: frozenset({VideoProcessingStatus.PROCESSING}),
    VideoProcessingStatus.COMPLETED: frozenset(),
}


def get_video(db: Session, video_id) -> Video:
    """Load a video with its owner and latest event data."""

    video = db.scalar(
        select(Video)
        .options(joinedload(Video.owner), joinedload(Video.upload_history))
        .where(Video.id == video_id)
    )
    if video is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return video


def update_video_status(
    db: Session,
    video: Video,
    new_status: VideoProcessingStatus,
    notes: str | None,
) -> Video:
    """Apply and record one valid processing lifecycle transition."""

    if new_status == video.processing_status:
        return video
    if new_status not in ALLOWED_TRANSITIONS.get(video.processing_status, frozenset()):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change video status from {video.processing_status} to {new_status}",
        )

    video.processing_status = new_status
    event = UploadHistory(
        video_id=video.id,
        status=UploadStatus(new_status),
        notes=notes or f"Video status changed to {new_status}.",
    )
    video.upload_history.append(event)
    db.commit()
    db.refresh(video)
    return video


def reconcile_terminal_transcript_statuses(db: Session, user_id: int | None = None) -> int:
    """Persist only evidence-backed outcomes for videos stuck in PROCESSING."""

    query = (
        select(Video)
        .options(joinedload(Video.upload_history), joinedload(Video.transcript))
        .where(Video.processing_status == VideoProcessingStatus.PROCESSING)
    )
    if user_id is not None:
        query = query.where(Video.user_id == user_id)

    reconciled = 0
    for video in db.scalars(query).unique().all():
        if video.transcript is None:
            continue
        if video.transcript.status == TranscriptStatus.COMPLETED:
            update_video_status(
                db,
                video,
                VideoProcessingStatus.COMPLETED,
                "Reconciled from completed transcript evidence.",
            )
            reconciled += 1
        elif video.transcript.status == TranscriptStatus.FAILED:
            update_video_status(
                db,
                video,
                VideoProcessingStatus.FAILED,
                video.transcript.error_message or "Reconciled from failed transcript evidence.",
            )
            reconciled += 1
    return reconciled