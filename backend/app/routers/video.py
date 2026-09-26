import logging
import mimetypes
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
from app.schemas.user import UserRole
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import Transcript, TranscriptStatus
from app.models.video import Video
from app.schemas.video import OwnedVideoResponse, VideoPipelineStatusResponse, VideoResponse, VideoStatusResponse
from app.services.ffmpeg_service import extract_audio, process_video
from app.services.highlight_service import extract_highlights_for_key_moments
from app.services.key_moment_service import detect_key_moments, save_key_moments
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


def remove_file(path: Path | str) -> None:
    """Best-effort cleanup for a file created during upload or processing."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


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
        db.commit()

        logger.info("Starting FFmpeg processing for video_id: %s", video_id)
        succeeded = process_video(
            input_path=input_path,
            output_path=output_path,
        )
        if not succeeded:
            logger.error("Video processing failed for video %s", video_id)
            transcript.status = TranscriptStatus.FAILED
            video.status = "failed"
            db.commit()
            return
        logger.info("FFmpeg processing completed for video_id: %s", video_id)
        
        # Update file_path to point to the processed video with proper audio encoding
        video.file_path = output_path
        db.commit()

        transcript.status = TranscriptStatus.PROCESSING
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
            video.status = "completed"
            db.commit()
            return

        logger.info("Starting Whisper transcription for video_id: %s", video_id)
        transcription = transcribe_audio(extraction.audio_path)
        if transcription.status != "completed":
            logger.warning(
                "Transcription failed for video %s: %s",
                video_id,
                transcription.error_code,
            )
            transcript.status = TranscriptStatus.FAILED
            video.status = "completed"
            db.commit()
            return
        logger.info("Whisper transcription completed for video_id: %s. Segment count: %d", video_id, len(transcription.segments))

        transcript.text = transcription.text
        transcript.language = transcription.language
        transcript.segments = transcription.segments
        transcript.status = TranscriptStatus.COMPLETED
        db.commit()
        db.refresh(transcript)
        logger.info("Starting summary initialization for video_id: %s", video_id)
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
        else:
            summary.short_summary = None
            summary.detailed_summary = None
            summary.status = SummaryStatus.PENDING
        logger.info("Summary initialization completed for video_id: %s", video_id)

        segments = transcript.segments
        if not segments:
            logger.info("No transcription segments for video_id: %s, skipping Module 3", video_id)
            video.status = "completed"
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
        db.commit()
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
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.status = "failed"
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
    return (
        db.query(Video)
        .filter(Video.user_id == current_user.id)
        .order_by(Video.uploaded_at.desc())
        .all()
    )


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
            else "PROCESSING" if video_status in {"PROCESSING", "VALIDATING", "FFMPEG_PROCESSING", "AI_PROCESSING"}
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
