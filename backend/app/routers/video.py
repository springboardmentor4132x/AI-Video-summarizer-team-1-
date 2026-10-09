import logging
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
from app.models.key_moment import KeyMoment
from app.schemas.video import VideoResponse, VideoStatusResponse
from app.services.ffmpeg_service import extract_audio, process_video
from app.services.summarization_service import summarize_transcript
from app.services.highlight_service import extract_highlights_for_key_moments
from app.services.key_moment_service import detect_key_moments, save_key_moments
from app.services.transcription_service import transcribe_audio

from sqlalchemy import BigInteger, Float, Column

file_size = Column(BigInteger, nullable=False, default=0)
duration = Column(Float, nullable=True)   # seconds

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
        
        video.file_path = output_path
        
        # --- NEW CODE: EXTRACT FILE SIZE & DURATION ---
        try:
            import subprocess
            
            # 1. Get file size in bytes
            video.file_size_bytes = Path(output_path).stat().st_size
            
            # 2. Get duration in seconds using ffprobe
            duration_cmd = [
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration", "-of",
                "default=noprint_wrappers=1:nokey=1", str(output_path)
            ]
            duration_str = subprocess.check_output(duration_cmd, text=True).strip()
            if duration_str:
                video.duration_seconds = int(float(duration_str))
        except Exception as e:
            logger.warning(f"Could not extract size/duration for video {video_id}: {e}")
        # --- END NEW CODE ---
        
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
            try:
                summary = Summary(transcript_id=transcript.id, status=SummaryStatus.PROCESSING)
                db.add(summary)
                db.commit()
            except Exception:
                db.rollback()
        else:
            summary.short_summary = None
            summary.detailed_summary = None
            summary.status = SummaryStatus.PROCESSING
            db.commit()
            
        # Actually generate the AI Summary automatically!
        try:
            logger.info("Generating AI summary in background...")
            sum_result = summarize_transcript(transcript)
            summary.short_summary = sum_result.short_summary
            summary.detailed_summary = sum_result.detailed_summary
            summary.status = SummaryStatus.COMPLETED
            db.commit()
            logger.info("Background summary generation completed!")
        except Exception as e:
            logger.error(f"Background summary generation failed: {e}")
            summary.status = SummaryStatus.FAILED
            db.commit()

        segments = transcript.segments or []
        if not segments:
            logger.info("No transcription segments for video_id: %s, skipping Module 3", video_id)
            video.status = "completed"
            db.commit()
            return

        logger.info("Starting Module 3 key moments detection for video_id: %s", video_id)
        segments = transcript.segments if hasattr(transcript, 'segments') else []
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
        filename=file.filename,
        file_path=str(input_path),
        status="uploaded",
        file_size=total_size,
        duration=get_duration(str(input_path)),
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


@router.get("/", response_model=list[VideoResponse])
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


@router.get("/status", response_model=list[VideoResponse])
def list_video_statuses(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return processing status records for the authenticated user's videos."""
    return (
        db.query(Video)
        .filter(Video.user_id == current_user.id)
        .order_by(Video.uploaded_at.desc())
        .all()
    )


@router.get("/history", response_model=list[VideoResponse])
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


@router.get("/media/videos/{video_id}")
@router.get("/media/videos/{user_id}/{video_id}")
def get_video_media(
    video_id: int,
    user_id: int = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Serve only the authenticated user's uploaded source video."""
    # The DB query strictly enforces that the current user owns this video
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    
    if video is None or not Path(video.file_path).is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
        
    return FileResponse(video.file_path, media_type="video/mp4", filename=video.filename)

from pydantic import BaseModel
import subprocess

class YouTubeRequest(BaseModel):
    youtube_url: str

@router.post("/youtube", response_model=VideoResponse, status_code=status.HTTP_201_CREATED)
async def process_youtube_video(
    payload: YouTubeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.CONTENT_CREATOR, UserRole.EDUCATOR]))
):
    """Download and process a YouTube video."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    video_uuid = str(uuid4())
    input_path = UPLOAD_DIR / f"{video_uuid}.mp4"
    output_path = UPLOAD_DIR / f"{video_uuid}_processed.mp4"
    
    video = Video(
        user_id=current_user.id,
        filename=f"YouTube Video - {video_uuid[:8]}",
        file_path=str(input_path),
        status="uploading",
    )
    db.add(video)
    db.commit()
    db.refresh(video)

    def download_and_process(vid_id, yt_url, in_path, out_path):
        db_bg = SessionLocal()
        vid = db_bg.query(Video).filter(Video.id == vid_id).first()
        try:
            logger.info(f"Starting YouTube download for: {yt_url}")
            
            # capture_output lets us see exactly why YouTube blocks it
            result = subprocess.run([
                "yt-dlp", 
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/mp4", 
                "-o", str(in_path), 
                yt_url
            ], capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"yt-dlp failed! Error: {result.stderr}")
                vid.status = "failed"
                db_bg.commit()
                return
            
            logger.info("YouTube download successful!")
            vid.status = "uploaded"
            db_bg.commit()
            db_bg.close()
            
            # Send to standard AI processing pipeline
            process_video_background(vid_id, str(in_path), str(out_path))
        except Exception as e:
            logger.error(f"Unexpected error in YouTube script: {str(e)}")
            vid.status = "failed"
            db_bg.commit()
            db_bg.close()

    background_tasks.add_task(download_and_process, video.id, payload.youtube_url, input_path, output_path)
    return video

@router.delete("/{video_id}")
def delete_video_endpoint(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Permanently delete a video and its files."""
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")
        
    # Delete the physical mp4 file from your hard drive
    if video.file_path:
        remove_file(video.file_path)
        
    # Delete from the database
    db.delete(video)
    db.commit()
    
    return {"message": "Video deleted successfully", "video_id": video.id}

    from app.models.key_moment import KeyMoment

@router.get("/{video_id}/mcqs")
def get_video_mcqs(
    video_id: int, 
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Fetch or generate MCQs for a specific video."""
    video = db.query(Video).filter(Video.id == video_id).first()
    if not video:
        raise HTTPException(status_code=404, detail="Video not found")

    moments = db.query(KeyMoment).filter(KeyMoment.video_id == video_id).all()
    mcqs = []
    
    # Generate 3 different questions per Key Moment to ensure a large pool!
    if moments:
        for m in moments:
            # Question Variation 1
            mcqs.append({
                "question": f"Regarding the topic '{m.topic or 'the video'}', which of the following best describes the takeaway at {int(m.start_time)} seconds?",
                "options": [m.text, "This section was about off-topic remarks.", "The speaker contradicted this point.", "None of the above."],
                "correct_answer": m.text,
                "explanation": f"Based on the AI-detected key moment: '{m.title}'.",
                "difficulty": "Medium",
                "topic": m.topic or "General",
                "source": "Key Moments",
                "timestamp": m.start_time
            })
            # Question Variation 2
            mcqs.append({
                "question": f"What is the main significance of the section titled '{m.title}'?",
                "options": [m.text, "It introduces the speaker.", "It concludes the video.", "It is a sponsor shoutout."],
                "correct_answer": m.text,
                "explanation": f"This is the core detail from {int(m.start_time)}s.",
                "difficulty": "Easy",
                "topic": m.topic or "General",
                "source": "Key Moments",
                "timestamp": m.start_time
            })
            # Question Variation 3
            mcqs.append({
                "question": f"At {int(m.start_time)} seconds, the video discusses {m.topic or 'a specific concept'}. Which statement is true?",
                "options": [m.text, "The concept was skipped entirely.", "It was mentioned but deemed unimportant.", "The video stated the exact opposite."],
                "correct_answer": m.text,
                "explanation": f"Derived directly from the '{m.title}' moment.",
                "difficulty": "Hard",
                "topic": m.topic or "General",
                "source": "Key Moments",
                "timestamp": m.start_time
            })
            
    # Fallback: if no key moments exist, generate a batch of 10 fallback questions so the UI never breaks
    if not mcqs:
        for i in range(10):
            mcqs.append({
                "question": f"Question {i+1}: What is the primary subject of this video?",
                "options": [video.filename, "Unknown Topic", "Audio Test", "None of the above"],
                "correct_answer": video.filename,
                "explanation": "This is a fallback question because AI key moments were not found.",
                "difficulty": "Easy",
                "topic": "General",
                "source": "Fallback",
                "timestamp": 0
            })
            
    return mcqs