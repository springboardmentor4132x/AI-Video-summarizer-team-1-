"""MCQ expectations derived from the processed video content."""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.auth.authorization import Permission, has_permission
from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.models import TranscriptStatus, User, Video, VideoProcessingStatus
from app.schemas.mcq import McqQuestionResponse
from app.services.gemini import GeminiProviderUnavailableError
from app.services.mcq import build_expected_mcqs

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/videos", tags=["mcqs"])


def _get_video(db: Session, video_id: UUID) -> Video:
    video = db.scalar(
        select(Video)
        .options(joinedload(Video.transcript), joinedload(Video.summary), joinedload(Video.key_moments))
        .where(Video.id == video_id)
    )
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


@router.get("/{video_id}/mcqs", response_model=list[McqQuestionResponse])
def get_expected_mcqs(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[McqQuestionResponse]:
    """Generate expected MCQs from the transcript, summary, and detected key moments."""
    video = _get_video(db, video_id)
    _require_access(user, video)
    if video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript is not available for this video. Generate the transcript first.")
    if video.transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="The transcript must be completed before MCQs can be generated.")

    logger.info(
        "MCQ generation request video_id=%s transcript_id=%s transcript_length=%s summary_id=%s key_moments_count=%s",
        str(video.id),
        str(video.transcript.id) if video.transcript else None,
        len(video.transcript.text or "") if video.transcript else 0,
        str(video.summary.id) if video.summary else None,
        len(video.key_moments or []),
    )

    try:
        questions = build_expected_mcqs(video)
    except GeminiProviderUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return [McqQuestionResponse.model_validate(question) for question in questions]
