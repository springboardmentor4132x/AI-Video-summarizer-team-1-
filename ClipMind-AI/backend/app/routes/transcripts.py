"""Protected transcript generation, viewing, editing, and download routes."""

from io import BytesIO
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.auth.authorization import Permission, has_permission
from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.models import Summary, Transcript, TranscriptStatus, User, Video, VideoProcessingStatus
from app.schemas.transcript import TranscriptResponse, TranscriptUpdateRequest
from app.services.speech_to_text import SpeechToTextError
from app.services.storage import CloudStorageError, LocalStorage, S3Storage, get_storage
from app.services.transcript import generate_transcript


router = APIRouter(prefix="/videos", tags=["transcripts"])


def _get_video(db: Session, video_id: UUID) -> Video:
    video = db.scalar(select(Video).options(joinedload(Video.transcript), joinedload(Video.summary)).where(Video.id == video_id))
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _can_view(user: User, video: Video) -> bool:
    if has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY):
        return True
    if has_permission(user, Permission.MANAGE_UPLOADED_VIDEOS) or has_permission(
        user, Permission.MANAGE_EDUCATIONAL_CONTENT
    ):
        return video.user_id == user.id
    return has_permission(user, Permission.VIEW_AVAILABLE_CONTENT) and video.processing_status == VideoProcessingStatus.COMPLETED


def _require_video_access(user: User, video: Video, editing: bool = False) -> None:
    if editing:
        permitted = has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY) or has_permission(
            user, Permission.MANAGE_UPLOADED_VIDEOS
        ) or has_permission(user, Permission.MANAGE_EDUCATIONAL_CONTENT)
        permitted = permitted and (has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY) or video.user_id == user.id)
    else:
        permitted = _can_view(user, video)
    if not permitted:
        raise HTTPException(status_code=403, detail="You do not have permission to access this transcript")


def _response(transcript: Transcript) -> TranscriptResponse:
    return TranscriptResponse.model_validate(transcript, from_attributes=True)


@router.post("/{video_id}/transcript", response_model=TranscriptResponse)
def create_transcript(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    storage: LocalStorage | S3Storage = Depends(get_storage),
) -> TranscriptResponse:
    video = _get_video(db, video_id)
    _require_video_access(user, video, editing=True)
    if video.transcript is not None and video.transcript.status == TranscriptStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Transcript generation is already in progress")
    if video.transcript is not None and video.transcript.status == TranscriptStatus.COMPLETED:
        return _response(video.transcript)
    try:
        transcript = generate_transcript(db, video, storage)
        return _response(transcript)
    except (SpeechToTextError, CloudStorageError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{video_id}/transcript", response_model=TranscriptResponse)
def get_transcript(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)) -> TranscriptResponse:
    video = _get_video(db, video_id)
    _require_video_access(user, video)
    if video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not generated yet")
    return _response(video.transcript)


@router.patch("/{video_id}/transcript", response_model=TranscriptResponse)
def update_transcript(
    video_id: UUID,
    request: TranscriptUpdateRequest,
    user: CurrentUser,
    db: Session = Depends(get_db),
) -> TranscriptResponse:
    video = _get_video(db, video_id)
    _require_video_access(user, video, editing=True)
    if video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not generated yet")
    video.transcript.text = request.text
    if request.segments is not None:
        video.transcript.segments = [segment.model_dump() for segment in request.segments]
    video.transcript.status = TranscriptStatus.COMPLETED
    video.transcript.error_message = None
    db.commit()
    db.execute(delete(Summary).where(Summary.video_id == video.id))
    db.commit()
    db.refresh(video.transcript)
    return _response(video.transcript)


@router.get("/{video_id}/transcript/download")
def download_transcript(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)) -> Response:
    video = _get_video(db, video_id)
    _require_video_access(user, video)
    if video.transcript is None or video.transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Transcript is not ready for download")
    filename = f"{video.filename.rsplit('.', 1)[0]}.txt"
    return Response(
        content=video.transcript.text,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )