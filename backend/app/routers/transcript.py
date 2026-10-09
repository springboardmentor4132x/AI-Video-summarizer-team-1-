import logging
from uuid import uuid4
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_role
from app.schemas.user import UserRole
from app.models.transcript import Transcript, TranscriptStatus
from app.models.video import Video
from app.schemas.transcript import TranscriptResponse, TranscriptUpdate
from app.services.ffmpeg_service import extract_audio
from app.services.transcription_service import transcribe_audio


logger = logging.getLogger(__name__)

# Directory used to stage temporary audio files during on-demand transcription.
# Mirrors the same constant used in the video router.
_BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = _BACKEND_DIR / "uploads"

router = APIRouter(tags=["transcripts"])


def _get_owned_video(video_id: int, db: Session, current_user) -> Video:
    """Return the video only when it is owned by current_user; 404 otherwise."""
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
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
            db.commit()
            raise HTTPException(
                status_code=500,
                detail="Audio could not be extracted from the video.",
            )

        result = transcribe_audio(extraction.audio_path)
        if result.status != "completed":
            transcript.status = TranscriptStatus.FAILED
            db.commit()
            raise HTTPException(
                status_code=500,
                detail="Whisper transcription failed.",
            )

        transcript.text = result.text
        transcript.language = result.language
        transcript.segments = result.segments
        transcript.status = TranscriptStatus.COMPLETED
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
    current_user=Depends(require_role([UserRole.CONTENT_CREATOR, UserRole.EDUCATOR])),
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

    content = transcript.text or ""
    safe_name = "transcript.txt"

    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"',
        },
    )