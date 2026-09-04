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
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_current_user
from app.models.transcript import Transcript, TranscriptStatus
from app.models.video import Video
from app.schemas.video import VideoResponse, VideoStatusResponse
from app.models.key_moment import KeyMoment
from app.services.ffmpeg_service import extract_audio, process_video
from app.services.transcription_service import transcribe_audio
from app.services.key_moment_service import (
    detect_key_moments,
    save_key_moments,
)
from app.services.highlight_service import (
    extract_highlights_for_key_moments,
)


router = APIRouter(
    prefix="/videos",
    tags=["videos"],
)

logger = logging.getLogger(__name__)


BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "uploads"

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}

MAX_FILE_SIZE = 500 * 1024 * 1024


def remove_file(path: Path | str) -> None:
    """Best-effort cleanup for a file."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def process_video_background(
    video_id: int,
    input_path: str,
    output_path: str,
):
    """
    Background pipeline:

    1. Process video
    2. Extract audio
    3. Transcribe audio
    4. Save transcript
    5. Detect key moments
    6. Save key moments
    7. Generate highlight clips
    8. Save highlight paths
    9. Mark video as completed
    """

    db = SessionLocal()

    succeeded = False
    audio_path = None

    try:
        # ---------------------------------------------------------
        # 1. Get video
        # ---------------------------------------------------------
        video = (
            db.query(Video)
            .filter(Video.id == video_id)
            .first()
        )

        if video is None:
            logger.error(
                "Video %s not found",
                video_id,
            )
            return

        # ---------------------------------------------------------
        # 2. Mark processing
        # ---------------------------------------------------------
        video.status = "processing"
        db.commit()

        logger.info(
            "Started processing video %s",
            video_id,
        )

        # ---------------------------------------------------------
        # 3. Process video with FFmpeg
        # ---------------------------------------------------------
        succeeded = process_video(
            input_path=input_path,
            output_path=output_path,
        )

        if not succeeded:
            logger.error(
                "Video processing failed for video %s",
                video_id,
            )

            video.status = "failed"
            db.commit()
            return

        logger.info(
            "Video processing completed for video %s",
            video_id,
        )

        # ---------------------------------------------------------
        # 4. Extract audio
        # ---------------------------------------------------------
        audio_path = (
            UPLOAD_DIR
            / f"{uuid4()}_transcription.wav"
        )

        extraction = extract_audio(
            video_path=input_path,
            audio_path=str(audio_path),
        )

        if (
            extraction.status != "completed"
            or not extraction.audio_path
        ):
            logger.warning(
                "Audio extraction failed for video %s: %s",
                video_id,
                extraction.error_code,
            )

            video.status = "completed"
            db.commit()
            return

        logger.info(
            "Audio extraction completed for video %s",
            video_id,
        )

        # ---------------------------------------------------------
        # 5. Transcribe audio
        # ---------------------------------------------------------
        transcription = transcribe_audio(
            extraction.audio_path
        )

        if transcription.status != "completed":
            logger.warning(
                "Transcription failed for video %s: %s",
                video_id,
                transcription.error_code,
            )

            video.status = "completed"
            db.commit()
            return

        logger.info(
            "Transcription completed for video %s",
            video_id,
        )

        # ---------------------------------------------------------
        # 6. Save transcript
        # ---------------------------------------------------------
        transcript = (
            db.query(Transcript)
            .filter(
                Transcript.video_id == video.id
            )
            .first()
        )

        if transcript is None:
            transcript = Transcript(
                video_id=video.id
            )
            db.add(transcript)

        transcript.text = transcription.text
        transcript.status = TranscriptStatus.COMPLETED

        db.flush()

        logger.info(
            "Transcript saved for video %s",
            video_id,
        )

        # ---------------------------------------------------------
        # 7. Get timestamped transcript segments
        # ---------------------------------------------------------
        segments = transcription.segments or []

        if not segments:
            logger.warning(
                "No transcript segments available for video %s",
                video_id,
            )

            video.status = "completed"
            db.commit()
            return

        # ---------------------------------------------------------
        # 8. Detect key moments
        # ---------------------------------------------------------
        moments = detect_key_moments(
            segments,
            threshold=0.30,
            max_moments=10,
        )

        logger.info(
            "Detected %s key moments for video %s",
            len(moments),
            video_id,
        )

        # ---------------------------------------------------------
        # 9. Save key moments
        # ---------------------------------------------------------
        saved_moments = save_key_moments(
            db=db,
            video_id=video.id,
            moments=moments,
        )

        logger.info(
            "Saved %s key moments for video %s",
            len(saved_moments),
            video_id,
        )

        # ---------------------------------------------------------
        # 10. Generate highlight videos
        # ---------------------------------------------------------
        highlight_dir = (
            UPLOAD_DIR
            / "highlights"
            / str(video.id)
        )

        highlight_results = (
            extract_highlights_for_key_moments(
                video_path=input_path,
                moments=saved_moments,
                output_dir=highlight_dir,
            )
        )

        logger.info(
            "Generated %s highlight results for video %s",
            len(highlight_results),
            video_id,
        )

        # ---------------------------------------------------------
        # 11. Save generated highlight paths
        # ---------------------------------------------------------
        successful_highlights = 0

        for index, moment in enumerate(saved_moments):
            result = (
                highlight_results[index]
                if index < len(highlight_results)
                else None
            )

            if result is None:
                logger.warning(
                    "No highlight result returned for key moment %s "
                    "of video %s",
                    moment.id,
                    video_id,
                )
                continue

            if result.status == "completed":
                moment.highlight_path = (
                    result.highlight_path
                )

                successful_highlights += 1

            else:
                logger.warning(
                    "Highlight generation failed "
                    "for key moment %s of video %s: %s",
                    moment.id,
                    video_id,
                    result.error_code,
                )

        db.commit()

        logger.info(
            "Generated %s/%s highlights for video %s",
            successful_highlights,
            len(saved_moments),
            video_id,
        )

        # ---------------------------------------------------------
        # 12. Mark video completed
        # ---------------------------------------------------------
        video.status = "completed"
        db.commit()

        logger.info(
            "Finished processing video %s",
            video_id,
        )

    except Exception:
        logger.exception(
            "Unexpected error while processing video %s",
            video_id,
        )

        db.rollback()

        try:
            video = (
                db.query(Video)
                .filter(Video.id == video_id)
                .first()
            )

            if video:
                video.status = "failed"
                db.commit()

        except Exception:
            db.rollback()

    finally:
        # ---------------------------------------------------------
        # Cleanup temporary audio
        # ---------------------------------------------------------
        if audio_path is not None:
            remove_file(audio_path)

        # ---------------------------------------------------------
        # Remove processed output if processing failed
        # ---------------------------------------------------------
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
    current_user=Depends(get_current_user),
):
    """
    Upload a video for the authenticated user.
    """

    try:
        # ---------------------------------------------------------
        # Validate filename
        # ---------------------------------------------------------
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is required",
            )

        original_filename = Path(
            file.filename
        ).name

        extension = Path(
            original_filename
        ).suffix.lower()

        # ---------------------------------------------------------
        # Validate extension
        # ---------------------------------------------------------
        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Unsupported video format",
            )

        # ---------------------------------------------------------
        # Create upload directory
        # ---------------------------------------------------------
        try:
            UPLOAD_DIR.mkdir(
                parents=True,
                exist_ok=True,
            )
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Unable to prepare video upload storage.",
            ) from exc

        # ---------------------------------------------------------
        # Generate unique file paths
        # ---------------------------------------------------------
        unique_name = (
            f"{uuid4()}{extension}"
        )

        input_path = (
            UPLOAD_DIR / unique_name
        )

        output_path = (
            UPLOAD_DIR
            / f"{uuid4()}_processed.mp4"
        )

        total_size = 0

        # ---------------------------------------------------------
        # Save uploaded file
        # ---------------------------------------------------------
        try:
            with input_path.open("wb") as buffer:

                while True:
                    chunk = await file.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > MAX_FILE_SIZE:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                "Video file is too large. "
                                "Maximum size is 500 MB."
                            ),
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

    # -------------------------------------------------------------
    # Create database record
    # -------------------------------------------------------------
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

    # -------------------------------------------------------------
    # Start background processing
    # -------------------------------------------------------------
    background_tasks.add_task(
        process_video_background,
        video.id,
        str(input_path),
        str(output_path),
    )

    return video


@router.get(
    "/{video_id}/status",
    response_model=VideoStatusResponse,
)
def get_video_status(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the processing status for a video
    owned by the current user.
    """

    video = (
        db.query(Video)
        .filter(
            Video.id == video_id,
            Video.user_id == current_user.id,
        )
        .first()
    )

    if video is None:
        raise HTTPException(
            status_code=404,
            detail="Video not found",
        )

    return video