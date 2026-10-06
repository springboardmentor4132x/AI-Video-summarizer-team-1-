import logging
from datetime import datetime, timezone
from uuid import uuid4
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_role
from app.schemas.user import UserRole
from app.models.transcript import Transcript, TranscriptStatus
from app.models.video import Video
from app.models.learning import AuditLog, ClassroomMember, ClassroomResource
from app.dependencies.video_access import learner_has_shared_access
from app.schemas.transcript import TranscriptResponse, TranscriptUpdate
from app.schemas.admin import TranscriptSearchMatch, TranscriptSearchResponse
from app.services.ffmpeg_service import extract_audio
from app.services.transcription_service import transcribe_audio


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _duration_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if started_at is None or completed_at is None:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    else:
        started_at = started_at.astimezone(timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    else:
        completed_at = completed_at.astimezone(timezone.utc)
    return max(0.0, (completed_at - started_at).total_seconds())


# Directory used to stage temporary audio files during on-demand transcription.
# Mirrors the same constant used in the video router.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = _BACKEND_DIR / "uploads"

router = APIRouter(tags=["transcripts"])


def _get_owned_video(video_id: int, db: Session, current_user) -> Video:
    """Return the video only when it is owned by current_user; 404 otherwise."""
    role = str(getattr(current_user, "role", "")).title()
    query = db.query(Video).filter(Video.id == video_id)
    if role != UserRole.ADMINISTRATOR.value:
        query = query.filter(Video.user_id == current_user.id)
    video = query.first()
    if video is None and str(getattr(current_user, "role", "")).title() == UserRole.LEARNER.value and learner_has_shared_access(db, video_id, current_user.id):
        video = db.query(Video).filter(Video.id == video_id, Video.status == "completed").first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


def _get_owned_transcript(video_id: int, db: Session, current_user) -> Transcript:
    """Return the transcript for a video owned by current_user; 404 otherwise."""
    video = _get_owned_video(video_id, db, current_user)
    if video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return video.transcript


# ---------------------------------------------------------------------------
# GET /transcripts/search — search the authenticated user's transcript data
# ---------------------------------------------------------------------------

@router.get("/transcripts/search", response_model=TranscriptSearchResponse)
def search_transcripts(
    q: str = Query(..., min_length=2, max_length=200),
    video_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Search completed transcript text and timestamped segments owned by the user."""
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Search query is required")

    rows = (
        db.query(Transcript)
        .join(Video, Transcript.video_id == Video.id)
        .filter(Transcript.status == TranscriptStatus.COMPLETED)
    )
    if str(getattr(current_user, "role", "")).title() != UserRole.LEARNER.value:
        rows = rows.filter(Video.user_id == current_user.id)
    else:
        from app.models.learning import SharedSummary
        shared_ids = db.query(SharedSummary.video_id).filter(SharedSummary.audience == "students").distinct()
        class_ids = db.query(ClassroomResource.resource_id).join(ClassroomMember, ClassroomMember.classroom_id == ClassroomResource.classroom_id).filter(ClassroomResource.resource_type == "video", ClassroomMember.learner_id == current_user.id)
        rows = rows.filter((Video.id.in_(shared_ids)) | (Video.id.in_(class_ids)))
    if video_id is not None:
        rows = rows.filter(Video.id == video_id)

    needle = query.casefold()
    results: list[TranscriptSearchMatch] = []
    for transcript in rows.order_by(Video.uploaded_at.desc()).all():
        segments = transcript.segments or []
        matched_segments = [
            segment
            for segment in segments
            if isinstance(segment, dict)
            and needle in str(segment.get("text", "")).casefold()
        ]
        if needle not in (transcript.text or "").casefold() and not matched_segments:
            continue

        if matched_segments:
            for segment in matched_segments:
                results.append(
                    TranscriptSearchMatch(
                        video_id=transcript.video_id,
                        filename=transcript.video.filename,
                        transcript_id=transcript.id,
                        status=transcript.status.value,
                        text=str(segment.get("text", "")),
                        start_time=segment.get("start"),
                        end_time=segment.get("end"),
                    )
                )
                if len(results) >= limit:
                    return TranscriptSearchResponse(query=query, results=results)
        else:
            results.append(
                TranscriptSearchMatch(
                    video_id=transcript.video_id,
                    filename=transcript.video.filename,
                    transcript_id=transcript.id,
                    status=transcript.status.value,
                    text=transcript.text or "",
                )
            )
            if len(results) >= limit:
                break

    return TranscriptSearchResponse(query=query, results=results)


# ---------------------------------------------------------------------------
# GET  /transcripts/{video_id}   (legacy alias)
# GET  /videos/{video_id}/transcript
# ---------------------------------------------------------------------------

@router.get("/transcripts/{video_id}", response_model=TranscriptResponse)
def get_transcript(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return _get_owned_transcript(video_id, db, current_user)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def get_video_transcript(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return _get_owned_transcript(video_id, db, current_user)


# ---------------------------------------------------------------------------
# POST /videos/{video_id}/transcript  — on-demand transcript generation
# ---------------------------------------------------------------------------

@router.post("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def generate_video_transcript(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.CONTENT_CREATOR, UserRole.EDUCATOR])),
):
    """Generate (or regenerate) a transcript for the authenticated user's video.

    * If a COMPLETED transcript already exists it is returned immediately
      without re-running Whisper.
    * If no transcript row exists one is created and Whisper is run
      synchronously.
    * If a previous attempt FAILED the row is reused and Whisper is
      retried.
    * Returns 409 if the video file cannot be found on disk (video not yet
      processed by the background pipeline).
    """
    video = _get_owned_video(video_id, db, current_user)

    # Ensure the source video file actually exists before attempting audio
    # extraction; the background pipeline may not have run yet.
    if not Path(video.file_path).is_file():
        raise HTTPException(
            status_code=409,
            detail="Video file is not available for transcription yet. "
                   "Wait for video processing to complete.",
        )

    # Retrieve or create the transcript row.
    transcript = video.transcript
    if transcript is None:
        transcript = Transcript(video_id=video.id, status=TranscriptStatus.PENDING)
        db.add(transcript)
        db.flush()

    # Short-circuit: nothing to do if transcription already succeeded.
    if transcript.status == TranscriptStatus.COMPLETED:
        return transcript

    # Guard against concurrent generation requests.
    if transcript.status == TranscriptStatus.PROCESSING:
        raise HTTPException(
            status_code=409,
            detail="Transcript generation is already in progress.",
        )

    transcript.status = TranscriptStatus.PROCESSING
    transcript.processing_started_at = _utc_now()
    transcript.processing_completed_at = None
    transcript.processing_duration_seconds = None
    transcript.error_code = None
    transcript.error_message = None
    video.processing_stage = "transcribing"
    video.processing_started_at = transcript.processing_started_at
    video.processing_error_code = None
    video.processing_error_message = None
    db.commit()

    audio_path = UPLOAD_DIR / f"{uuid4()}_transcription.wav"
    try:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        extraction = extract_audio(
            video_path=video.file_path,
            audio_path=str(audio_path),
        )
        if extraction.status != "completed" or not extraction.audio_path:
            transcript.status = TranscriptStatus.FAILED
            transcript.error_code = extraction.error_code or "audio_extraction_failed"
            transcript.error_message = extraction.error_message or "Audio could not be extracted from the video."
            transcript.processing_completed_at = _utc_now()
            transcript.processing_duration_seconds = _duration_seconds(transcript.processing_started_at, transcript.processing_completed_at)
            video.processing_stage = "failed"
            video.processing_error_code = transcript.error_code
            video.processing_error_message = transcript.error_message
            video.processing_completed_at = transcript.processing_completed_at
            video.status = "failed"
            db.commit()
            raise HTTPException(
                status_code=500,
                detail="Audio could not be extracted from the video.",
            )

        result = transcribe_audio(extraction.audio_path)
        if result.status != "completed":
            transcript.status = TranscriptStatus.FAILED
            transcript.error_code = result.error_code or "transcription_failed"
            transcript.error_message = result.error_message or "Whisper transcription failed."
            transcript.processing_completed_at = _utc_now()
            transcript.processing_duration_seconds = _duration_seconds(transcript.processing_started_at, transcript.processing_completed_at)
            video.processing_stage = "failed"
            video.processing_error_code = transcript.error_code
            video.processing_error_message = transcript.error_message
            video.processing_completed_at = transcript.processing_completed_at
            video.status = "failed"
            db.commit()
            raise HTTPException(
                status_code=500,
                detail="Whisper transcription failed.",
            )

        transcript.text = result.text
        transcript.language = result.language
        transcript.segments = result.segments
        transcript.status = TranscriptStatus.COMPLETED
        transcript.error_code = None
        transcript.error_message = None
        transcript.processing_completed_at = _utc_now()
        transcript.processing_duration_seconds = _duration_seconds(transcript.processing_started_at, transcript.processing_completed_at)
        video.processing_stage = "completed"
        video.processing_completed_at = transcript.processing_completed_at
        video.processing_error_code = None
        video.processing_error_message = None
        video.status = "completed"
        db.commit()
        db.refresh(transcript)
        return transcript

    except HTTPException:
        raise
    except Exception:
        logger.exception("Unexpected error during on-demand transcription for video %s", video_id)
        db.rollback()
        try:
            transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
            if transcript is not None:
                transcript.status = TranscriptStatus.FAILED
                transcript.error_code = transcript.error_code or "transcription_failed"
                transcript.error_message = transcript.error_message or "Transcript generation failed."
                transcript.processing_completed_at = _utc_now()
                if transcript.processing_started_at is not None:
                    transcript.processing_duration_seconds = _duration_seconds(
                        transcript.processing_started_at,
                        transcript.processing_completed_at,
                    )
                video = db.query(Video).filter(Video.id == video_id).first()
                if video:
                    video.status = "failed"
                    video.processing_stage = "failed"
                    video.processing_error_code = transcript.error_code
                    video.processing_error_message = transcript.error_message
                    video.processing_completed_at = transcript.processing_completed_at
                db.commit()
        except Exception:
            db.rollback()
        raise HTTPException(status_code=500, detail="Transcript generation failed.")
    finally:
        try:
            audio_path.unlink(missing_ok=True)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# PATCH /videos/{video_id}/transcript  — update transcript text
# ---------------------------------------------------------------------------

@router.patch("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def update_video_transcript(
    video_id: int,
    payload: TranscriptUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(UserRole.EDUCATOR)),
):
    """Update editable fields on an existing COMPLETED transcript.

    Only fields explicitly provided in the request body are changed;
    timestamps, segments, and status are preserved unless the caller
    supplies them.
    """
    transcript = _get_owned_transcript(video_id, db, current_user)

    if transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Only a completed transcript can be edited.",
        )

    if payload.text is not None:
        transcript.text = payload.text
    if payload.language is not None:
        transcript.language = payload.language
    if payload.segments is not None:
        transcript.segments = payload.segments

    db.add(AuditLog(actor_id=current_user.id, action="educator.transcript.edit", resource=f"video:{video_id}"))

    db.commit()
    db.refresh(transcript)
    return transcript


# ---------------------------------------------------------------------------
# GET /videos/{video_id}/transcript/download  — plain-text download
# ---------------------------------------------------------------------------

@router.get("/videos/{video_id}/transcript/download")
def download_video_transcript(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the transcript text as a downloadable plain-text file.

    Generates the response body dynamically from the stored ``text``
    column — no temporary files are created.
    """
    transcript = _get_owned_transcript(video_id, db, current_user)

    if transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Transcript is not yet available for download.",
        )

    video = _get_owned_video(video_id, db, current_user)
    
    # Prefer explicit text content if available, or return empty if explicitly None
    if transcript.text:
        content = transcript.text.strip() if transcript.text.strip() else ""
    elif transcript.text is None:
        # Explicitly None means no content
        content = ""
    else:
        # Fall back to rendering segments if text is not available
        segments = transcript.segments or []
        rendered_segments = []
        if segments:
            for segment in segments:
                if not isinstance(segment, dict) or not isinstance(segment.get("text"), str):
                    continue
                start = segment.get("start_time", segment.get("start"))
                try:
                    seconds = max(0.0, float(start))
                    timestamp = f"[{int(seconds // 60):02d}:{seconds % 60:05.2f}]"
                except (TypeError, ValueError):
                    timestamp = "[--:--]"
                rendered_segments.append(f"{timestamp} {segment['text'].strip()}")
        
        if rendered_segments:
            lines = [f"Video: {video.filename}", "", "Transcript", ""] + rendered_segments
            content = "\n".join(lines) + "\n"
        else:
            content = ""

    import re
    safe_name = re.sub(r'[^a-zA-Z0-9._-]', '_', video.filename.rsplit('.', 1)[0])
    safe_name = f"{safe_name}_transcript.txt"

    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )
