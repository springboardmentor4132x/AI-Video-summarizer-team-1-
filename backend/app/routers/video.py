from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal, get_db
from backend.app.dependencies.auth import get_current_user
from backend.app.models.video import Video
from backend.app.schemas.video import VideoResponse
from backend.app.services.ffmpeg_service import process_video


router = APIRouter(
    prefix="/videos",
    tags=["videos"],
)


UPLOAD_DIR = Path("uploads/videos")

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".avi",
    ".mkv",
    ".webm",
}

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


def process_video_background(video_id: int, input_path: str, output_path: str):
    """
    Process a video in the background and update its database status.
    """

    db = SessionLocal()

    try:
        video = db.query(Video).filter(Video.id == video_id).first()

        if video is None:
            return

        video.status = "processing"
        db.commit()

        success = process_video(
            input_path=input_path,
            output_path=output_path,
        )

        if success:
            video.status = "completed"
        else:
            video.status = "failed"

        db.commit()

    except Exception:
        db.rollback()

        video = db.query(Video).filter(Video.id == video_id).first()

        if video:
            video.status = "failed"
            db.commit()

    finally:
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

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

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
                    input_path.unlink(missing_ok=True)

                    raise HTTPException(
                        status_code=413,
                        detail="Video file is too large. Maximum size is 500 MB.",
                    )

                buffer.write(chunk)

    finally:
        await file.close()

    video = Video(
        user_id=current_user.id,
        filename=original_filename,
        file_path=str(input_path),
        status="uploaded",
    )

    db.add(video)
    db.commit()
    db.refresh(video)

    background_tasks.add_task(
        process_video_background,
        video.id,
        str(input_path),
        str(output_path),
    )

    return video