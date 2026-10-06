import logging
import mimetypes
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_current_user, require_role
from app.dependencies.video_access import learner_accessible_videos, learner_has_shared_access
from app.models.learning import AuditLog
from app.schemas.user import UserRole
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import Transcript, TranscriptStatus
from app.models.video import Video
from app.schemas.video import OwnedVideoResponse, VideoPipelineStatusResponse, VideoResponse, VideoStatusResponse
from app.services.ffmpeg_service import extract_audio, process_video
from app.services.highlight_service import extract_highlights_for_key_moments
from app.services.key_moment_service import detect_key_moments, save_key_moments
from app.services.summarization_service import summarize_transcript
from app.services.transcription_service import transcribe_audio


router = APIRouter(
    prefix="/videos",
    tags=["videos"],
)

logger = logging.getLogger(__name__)


BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "uploads"

# Configure dedicated background tasks logger once per log file.
log_path = (BACKEND_DIR / "bg_tasks.log").resolve()
has_file_handler = any(
    isinstance(handler, logging.FileHandler)
    and Path(handler.baseFilename).resolve() == log_path
    for handler in logger.handlers
)
if not has_file_handler:
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
logger.setLevel(logging.INFO)

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}

MAX_FILE_SIZE = 500 * 1024 * 1024
PROCESSING_VIDEO_STATUSES = {
    "PROCESSING",
    "VALIDATING",
    "FFMPEG_PROCESSING",
    "EXTRACTING_AUDIO",
    "TRANSCRIBING",
    "AI_PROCESSING",
}


def remove_file(path: Path | str) -> None:
    """Best-effort cleanup for a file created during upload or processing."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


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
    duration = (completed_at - started_at).total_seconds()
    return max(0.0, float(duration))


def _read_video_duration_seconds(path: str | Path | None) -> float | None:
    if not path:
        return None
    input_file = Path(path)
    if not input_file.is_file():
        return None
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nokey=1:noprint_wrappers=1",
                str(input_file),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    try:
        value = float(result.stdout.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _set_video_processing_failure(video: Video, code: str | None, message: str | None) -> None:
    finished_at = _utc_now()
    video.status = "failed"
    video.processing_stage = "failed"
    video.processing_error_code = code or "processing_failed"
    video.processing_error_message = message or "Video processing failed."
    video.processing_completed_at = finished_at


def process_video_background(
    video_id: int,
    input_path: str,
    output_path: str,
):
    """Run the video, transcript, key-moment, and highlight pipeline."""
    db = SessionLocal()
    succeeded = False
    audio_path = None
    transcript = None

    try:
        logger.info("Starting background processing for video_id: %s. Path: %s", video_id, input_path)
        video = db.query(Video).filter(Video.id == video_id).first()
        if video is None:
            logger.error("Video %s not found", video_id)
            return

        transcript = (
            db.query(Transcript)
            .filter(Transcript.video_id == video.id)
            .first()
        )
        if transcript is None:
            transcript = Transcript(
                video_id=video.id,
                status=TranscriptStatus.PENDING,
            )
            db.add(transcript)
            db.flush()

        video.status = "processing"
        video.processing_stage = "validating"
        video.processing_started_at = _utc_now()
        video.processing_error_code = None
        video.processing_error_message = None
        video.processing_completed_at = None
        video.duration_seconds = None
        transcript.error_code = None
        transcript.error_message = None
        transcript.processing_started_at = None
        transcript.processing_completed_at = None
        transcript.processing_duration_seconds = None
        db.commit()

        logger.info("Starting FFmpeg processing for video_id: %s", video_id)
        video.processing_stage = "processing"
        db.commit()
        succeeded = process_video(
            input_path=input_path,
            output_path=output_path,
        )
        if not succeeded:
            logger.error("Video processing failed for video %s", video_id)
            transcript.status = TranscriptStatus.FAILED
            transcript.error_code = "ffmpeg_failed"
            transcript.error_message = "Video processing failed while converting the uploaded file."
            transcript.processing_completed_at = _utc_now()
            transcript.processing_duration_seconds = _duration_seconds(video.processing_started_at, transcript.processing_completed_at)
            _set_video_processing_failure(video, "ffmpeg_failed", "Video processing failed while encoding the uploaded file.")
            db.commit()
            return
        logger.info("FFmpeg processing completed for video_id: %s", video_id)

        video.file_path = output_path
        video.duration_seconds = (
            _read_video_duration_seconds(output_path)
            or _read_video_duration_seconds(input_path)
            or _duration_seconds(video.processing_started_at, _utc_now())
            or 1
        )
        db.commit()

        video.processing_stage = "extracting_audio"
        db.commit()
        audio_path = UPLOAD_DIR / f"{uuid4()}_transcription.wav"
        extraction = extract_audio(
            video_path=input_path,
            audio_path=str(audio_path),
        )
        if extraction.status != "completed" or not extraction.audio_path:
            logger.warning(
                "Audio extraction failed for video %s: %s",
                video_id,
                extraction.error_code,
            )
            transcript.status = TranscriptStatus.FAILED
            transcript.error_code = getattr(extraction, "error_code", None) or "audio_extraction_failed"
            transcript.error_message = getattr(extraction, "error_message", None) or "Audio extraction failed."
            transcript.processing_completed_at = _utc_now()
            transcript.processing_duration_seconds = _duration_seconds(video.processing_started_at, transcript.processing_completed_at)
            _set_video_processing_failure(video, transcript.error_code, transcript.error_message)
            db.commit()
            return

        logger.info("Starting Whisper transcription for video_id: %s", video_id)
        transcript.status = TranscriptStatus.PROCESSING
        transcript.processing_started_at = _utc_now()
        transcript.error_code = None
        transcript.error_message = None
        transcript.processing_completed_at = None
        transcript.processing_duration_seconds = None
        video.processing_stage = "transcribing"
        db.commit()

        transcription = transcribe_audio(extraction.audio_path)
        if transcription.status != "completed":
            logger.warning(
                "Transcription failed for video %s: %s",
                video_id,
                transcription.error_code,
            )
            transcript.status = TranscriptStatus.FAILED
            transcript.error_code = getattr(transcription, "error_code", None) or "transcription_failed"
            transcript.error_message = getattr(transcription, "error_message", None) or "Whisper transcription failed."
            transcript.processing_completed_at = _utc_now()
            transcript.processing_duration_seconds = _duration_seconds(transcript.processing_started_at, transcript.processing_completed_at)
            _set_video_processing_failure(video, transcript.error_code, transcript.error_message)
            db.commit()
            return
        logger.info("Whisper transcription completed for video_id: %s. Segment count: %d", video_id, len(transcription.segments or []))

        transcript.text = transcription.text
        transcript.language = transcription.language
        transcript.segments = transcription.segments
        transcript.status = TranscriptStatus.COMPLETED
        transcript.processing_completed_at = _utc_now()
        transcript.processing_duration_seconds = _duration_seconds(transcript.processing_started_at, transcript.processing_completed_at)
        transcript.error_code = None
        transcript.error_message = None
        db.commit()
        db.refresh(transcript)

        logger.info("Starting summary generation for video_id: %s", video_id)
        summary = (
            db.query(Summary)
            .filter(Summary.transcript_id == transcript.id)
            .first()
        )
        if summary is None:
            summary = Summary(
                transcript_id=transcript.id,
                status=SummaryStatus.PENDING,
            )
            db.add(summary)
            db.flush()
        else:
            summary.short_summary = None
            summary.detailed_summary = None
            summary.status = SummaryStatus.PENDING
        summary.processing_started_at = _utc_now()
        summary.processing_completed_at = None
        summary.processing_duration_seconds = None
        summary.error_code = None
        summary.error_message = None
        db.commit()

        try:
            result = summarize_transcript(transcript)
            summary.short_summary = result.short_summary
            summary.detailed_summary = result.detailed_summary
            summary.status = SummaryStatus.COMPLETED
            summary.processing_completed_at = _utc_now()
            summary.processing_duration_seconds = _duration_seconds(summary.processing_started_at, summary.processing_completed_at)
            summary.error_code = None
            summary.error_message = None
            db.commit()
            logger.info("Summary generation completed for video_id: %s", video_id)
        except Exception as exc:
            logger.exception("Summary generation failed for video_id: %s", video_id)
            summary.status = SummaryStatus.FAILED
            summary.error_code = "summary_generation_failed"
            summary.error_message = "Summary generation failed."
            summary.processing_completed_at = _utc_now()
            summary.processing_duration_seconds = _duration_seconds(summary.processing_started_at, summary.processing_completed_at)
            db.commit()

        segments = transcript.segments or []
        if not segments:
            logger.info("No transcription segments for video_id: %s, skipping Module 3", video_id)
            video.status = "completed"
            video.processing_stage = "completed"
            video.processing_completed_at = _utc_now()
            video.duration_seconds = (
                _read_video_duration_seconds(output_path)
                or _read_video_duration_seconds(input_path)
                or _duration_seconds(video.processing_started_at, video.processing_completed_at)
                or video.duration_seconds
                or 1
            )
            db.commit()
            return

        logger.info("Starting Module 3 key moments detection for video_id: %s", video_id)
        moments = detect_key_moments(
            segments,
            threshold=0.30,
            max_moments=10,
        )
        saved_moments = save_key_moments(
            db=db,
            video_id=video.id,
            moments=moments,
        )
        logger.info("Module 3 key moments detection completed for video_id: %s. Key moment count: %d", video_id, len(saved_moments))

        highlight_dir = UPLOAD_DIR / "highlights" / str(video.id)
        highlight_results = extract_highlights_for_key_moments(
            video_path=input_path,
            moments=saved_moments,
            output_dir=highlight_dir,
        )

        for index, moment in enumerate(saved_moments):
            result = (
                highlight_results[index]
                if index < len(highlight_results)
                else None
            )
            if result is None:
                logger.warning(
                    "No highlight result for key moment %s of video %s",
                    moment.id,
                    video_id,
                )
                continue
            if result.status == "completed":
                moment.highlight_path = result.highlight_path
            else:
                logger.warning(
                    "Highlight generation failed for key moment %s of video %s: %s",
                    moment.id,
                    video_id,
                    result.error_code,
                )

        video.status = "completed"
        video.processing_stage = "completed"
        video.processing_completed_at = _utc_now()
        video.processing_error_code = None
        video.processing_error_message = None
        video.duration_seconds = (
            _read_video_duration_seconds(output_path)
            or _read_video_duration_seconds(input_path)
            or _duration_seconds(video.processing_started_at, video.processing_completed_at)
            or video.duration_seconds
            or 1
        )
        db.commit()
        succeeded = True
        logger.info("Background processing successfully completed for video_id: %s", video_id)

    except Exception:
        logger.exception("Unexpected error while processing video %s", video_id)
        db.rollback()
        try:
            transcript = (
                db.query(Transcript)
                .filter(Transcript.video_id == video_id)
                .first()
            )
            if transcript is not None and transcript.status != TranscriptStatus.COMPLETED:
                transcript.status = TranscriptStatus.FAILED
                transcript.processing_completed_at = _utc_now()
                if transcript.processing_started_at is not None:
                    transcript.processing_duration_seconds = _duration_seconds(
                        transcript.processing_started_at,
                        transcript.processing_completed_at,
                    )
                transcript.error_code = transcript.error_code or "processing_exception"
                transcript.error_message = transcript.error_message or "Processing failed unexpectedly."
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                _set_video_processing_failure(video, "processing_exception", "Processing failed unexpectedly.")
                db.commit()
        except Exception:
            db.rollback()

    finally:
        if audio_path is not None:
            remove_file(audio_path)
        if not succeeded:
            remove_file(output_path)
        db.close()


@router.post(
    "/upload",
    response_model=VideoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.CONTENT_CREATOR, UserRole.EDUCATOR])),
):
    """Upload a video for the authenticated user."""
    try:
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")

        original_filename = Path(file.filename).name
        extension = Path(original_filename).suffix.lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail="Unsupported video format")

        try:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Unable to prepare video upload storage.",
            ) from exc

        input_path = UPLOAD_DIR / f"{uuid4()}{extension}"
        output_path = UPLOAD_DIR / f"{uuid4()}_processed.mp4"
        total_size = 0

        try:
            with input_path.open("wb") as buffer:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail="Video file is too large. Maximum size is 500 MB.",
                        )
                    buffer.write(chunk)
        except HTTPException:
            remove_file(input_path)
            raise
        except Exception as exc:
            remove_file(input_path)
            raise HTTPException(
                status_code=500,
                detail="Unable to save uploaded video.",
            ) from exc
    finally:
        await file.close()

    video = Video(
        user_id=current_user.id,
        filename=original_filename,
        file_path=str(input_path),
        status="uploaded",
    )
    try:
        db.add(video)
        db.flush()
        db.refresh(video)
        db.add(AuditLog(actor_id=current_user.id, action="video.upload", resource=f"video:{video.id}"))
        db.commit()
    except Exception as exc:
        db.rollback()
        remove_file(input_path)
        raise HTTPException(
            status_code=500,
            detail="Unable to create video record.",
        ) from exc

    background_tasks.add_task(
        process_video_background,
        video.id,
        str(input_path),
        str(output_path),
    )
    return video


@router.get("/", response_model=list[OwnedVideoResponse])
def list_videos(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return videos uploaded by the authenticated user."""
    query = db.query(Video)
    if str(getattr(current_user, "role", "")).title() == UserRole.LEARNER.value:
        query = learner_accessible_videos(db, current_user.id)
    else:
        query = query.filter(Video.user_id == current_user.id)
    return query.order_by(Video.uploaded_at.desc()).all()


@router.get("/status", response_model=list[VideoPipelineStatusResponse])
def list_video_statuses(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return processing status records for the authenticated user's videos."""
    videos = (
        db.query(Video)
        .filter(Video.user_id == current_user.id)
        .order_by(Video.uploaded_at.desc())
        .all()
    )
    statuses = []
    for video in videos:
        transcript = video.transcript
        summary = transcript.summary if transcript else None
        video_status = str(video.status).upper()
        key_moments_status = (
            "FAILED" if video_status == "FAILED"
            else "COMPLETED" if video_status == "COMPLETED"
            else "PROCESSING" if video_status in PROCESSING_VIDEO_STATUSES
            else "NOT_STARTED"
        )
        statuses.append({
            "id": video.id,
            "filename": video.filename,
            "status": video.status,
            "uploaded_at": video.uploaded_at,
            "transcript_status": transcript.status.value.upper() if transcript else "NOT_STARTED",
            "summary_status": summary.status.value.upper() if summary else "NOT_STARTED",
            "key_moments_status": key_moments_status,
            "key_moment_count": len(video.key_moments or []),
        })
    return statuses


@router.get("/history", response_model=list[OwnedVideoResponse])
def list_upload_history(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return upload history derived from the authenticated user's videos."""
    return (
        db.query(Video)
        .filter(Video.user_id == current_user.id)
        .order_by(Video.uploaded_at.desc())
        .all()
    )


@router.get(
    "/{video_id}/status",
    response_model=VideoStatusResponse,
)
def get_video_status(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return the processing status for a video owned by the current user."""
    video = (
        db.query(Video)
        .filter(
            Video.id == video_id,
            Video.user_id == current_user.id,
        )
        .first()
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


@router.get("/media/videos/{user_id}/{video_id}")
def get_video_media(
    user_id: int,
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Serve only the authenticated user's uploaded source video."""
    if user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Video not found")
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None or not Path(video.file_path).is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    media_type = mimetypes.guess_type(video.filename)[0] or "application/octet-stream"
    return FileResponse(video.file_path, media_type=media_type, filename=video.filename)


@router.get("/{video_id}/media")
def get_owned_video_media(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Serve a video by ID, scoped to the authenticated owner."""
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None and str(getattr(current_user, "role", "")).title() == UserRole.LEARNER.value and learner_has_shared_access(db, video_id, current_user.id):
        video = db.query(Video).filter(Video.id == video_id, Video.status == "completed").first()
    if video is None or not Path(video.file_path).is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    media_type = mimetypes.guess_type(video.filename)[0] or "application/octet-stream"
    return FileResponse(video.file_path, media_type=media_type, filename=video.filename)


@router.delete("/{video_id}")
def delete_owned_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Delete an owned video and its associated transcript, summary, and moments."""
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    managed_root = UPLOAD_DIR.resolve()
    paths_to_remove = [Path(video.file_path)]
    paths_to_remove.extend(Path(moment.highlight_path) for moment in video.key_moments if moment.highlight_path)
    try:
        db.delete(video)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.exception("Unable to delete video_id=%s", video_id)
        raise HTTPException(status_code=500, detail="Video could not be deleted.") from exc

    for candidate in paths_to_remove:
        try:
            resolved = candidate.resolve()
            if resolved != managed_root and managed_root in resolved.parents:
                remove_file(resolved)
        except OSError:
            logger.warning("Unable to remove managed video artifact for video_id=%s", video_id)

    return {"message": "Video and associated data deleted successfully.", "video_id": str(video_id)}
