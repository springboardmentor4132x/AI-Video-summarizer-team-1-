"""Summary generation and retrieval routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.authorization import Permission, has_permission
from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.models import Summary, SummaryStatus, TranscriptStatus, User, Video, VideoProcessingStatus
from app.schemas.summary import SummaryResponse
from app.services.summary import SummaryError, summarize_transcript_with_gemini

router = APIRouter(prefix="/videos", tags=["summaries"])


def _get_video(db: Session, video_id: UUID) -> Video:
    video = db.scalar(select(Video).options(joinedload(Video.transcript), joinedload(Video.summary)).where(Video.id == video_id))
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _require_access(user: User, video: Video) -> None:
    is_admin = has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY)
    manages_videos = has_permission(user, Permission.MANAGE_UPLOADED_VIDEOS) or has_permission(
        user, Permission.MANAGE_EDUCATIONAL_CONTENT
    )
    can_view_completed = has_permission(user, Permission.VIEW_AVAILABLE_CONTENT) and video.processing_status == VideoProcessingStatus.COMPLETED
    if not (is_admin or (manages_videos and video.user_id == user.id) or can_view_completed):
        raise HTTPException(status_code=403, detail="You do not have permission to access this video")


def _duration_seconds(video: Video) -> int | None:
    if video.duration_seconds is not None:
        return video.duration_seconds
    if video.transcript is None:
        return None
    segments = video.transcript.segments or []
    return int(max((float(segment.get("end_time", 0)) for segment in segments), default=0)) or None


def _segment_transcript(video: Video) -> str:
    """Build summary input only from this video's validated stored segments."""
    return " ".join(
        str(segment.get("text", "")).strip()
        for segment in video.transcript.segments
        if isinstance(segment, dict) and str(segment.get("text", "")).strip()
    )


@router.post("/{video_id}/summary", response_model=SummaryResponse)
def generate_summary(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    regenerate: bool = False,
) -> SummaryResponse:
    """Generate and persist a summary for an authenticated creator's video."""
    video = _get_video(db, video_id)
    _require_access(user, video)
    if video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript is not available for this video. Generate the transcript first.")
    if video.transcript.status == TranscriptStatus.PROCESSING or video.transcript.status == TranscriptStatus.PENDING:
        raise HTTPException(status_code=409, detail="Transcript is still being generated.")
    if video.transcript.status == TranscriptStatus.FAILED:
        raise HTTPException(status_code=422, detail="Transcript generation failed. Please try again.")
    segment_text = _segment_transcript(video)
    if video.transcript.status != TranscriptStatus.COMPLETED or not segment_text or not video.transcript.segments:
        raise HTTPException(status_code=422, detail="Unable to generate a summary because no transcript content was found.")

    existing = video.summary
    if existing is not None:
        if existing.status == SummaryStatus.PROCESSING and not regenerate:
            raise HTTPException(status_code=409, detail="Summary generation is already in progress. Please wait for it to finish.")
        if existing.status == SummaryStatus.COMPLETED and not regenerate:
            return SummaryResponse.model_validate(existing, from_attributes=True)

    if existing is None:
        existing = Summary(video_id=video.id, transcript_id=video.transcript.id)
        db.add(existing)
    existing.status = SummaryStatus.PROCESSING
    existing.error_message = None
    db.commit()
    db.refresh(existing)

    try:
        generated = summarize_transcript_with_gemini(segment_text)
    except SummaryError as exc:
        existing.status = SummaryStatus.FAILED
        existing.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    existing.content = generated.long_summary
    existing.overview = generated.short_summary
    existing.main_points = generated.key_points
    existing.key_takeaways = generated.key_points
    existing.duration_seconds = _duration_seconds(video)
    existing.status = SummaryStatus.COMPLETED
    existing.error_message = None
    db.commit()
    db.refresh(existing)
    return SummaryResponse.model_validate(existing, from_attributes=True)


@router.post("/{video_id}/summary/retry", response_model=SummaryResponse)
def retry_summary(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> SummaryResponse:
    """Retry summary generation after a failed or stale attempt."""
    return generate_summary(video_id=video_id, user=user, db=db, regenerate=True)


@router.get("/{video_id}/summary", response_model=SummaryResponse)
def get_summary(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> SummaryResponse:
    """Return the saved summary for the current user's video."""
    video = _get_video(db, video_id)
    _require_access(user, video)
    if video.summary is None:
        raise HTTPException(status_code=404, detail="Summary does not exist")
    return SummaryResponse.model_validate(video.summary, from_attributes=True)
