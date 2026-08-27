from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_current_user
from app.models.video import Video
from app.schemas.video import VideoResponse, VideoStatusResponse
from app.services.ffmpeg_service import process_video


router = APIRouter(
    prefix="/videos",
    tags=["videos"],
)


BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "uploads"

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


def remove_file(path: Path | str) -> None:
    """Best-effort cleanup for a file created during upload or processing."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def process_video_background(video_id: int, input_path: str, output_path: str):
    """
    Process a video in the background and update its database status.
    """

    db = SessionLocal()

    succeeded = False

    try:
        video = db.query(Video).filter(Video.id == video_id).first()

        if video is None:
            return

        video.status = "processing"
        db.commit()

        succeeded = process_video(
            input_path=input_path,
            output_path=output_path,
        )

        if succeeded:
            video.status = "completed"
        else:
            video.status = "failed"

        db.commit()

    except Exception:
        db.rollback()

        try:
            video = db.query(Video).filter(Video.id == video_id).first()

            if video:
                video.status = "failed"
                db.commit()
        except Exception:
            db.rollback()

    finally:
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
        if not file.filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is required",
            )

        original_filename = Path(file.filename).name
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Unsupported video format",
            )

        try:
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(
                status_code=500,
                detail="Unable to prepare video upload storage.",
            ) from exc

        unique_name = f"{uuid4()}{extension}"
        input_path = UPLOAD_DIR / unique_name
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
        raise HTTPException(
            status_code=404,
            detail="Video not found",
        )

    return video
