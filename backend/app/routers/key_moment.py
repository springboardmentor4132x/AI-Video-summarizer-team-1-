from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.video import get_owned_video
from app.models.video import Video
from app.models.key_moment import KeyMoment
from app.schemas.key_moment import KeyMomentsResponse


router = APIRouter(
    prefix="/videos",
    tags=["key-moments"],
)

from fastapi import BackgroundTasks
from app.db.session import SessionLocal
from app.models.transcript import Transcript
from app.routers.video import generate_key_moments_task

def run_generate_key_moments(video_id: int, input_path: str, segments: list):
    db = SessionLocal()
    try:
        generate_key_moments_task(video_id, input_path, segments, db)
    finally:
        db.close()

@router.post(
    "/{video_id}/key-moments/generate",
    response_model=KeyMomentsResponse,
)
def generate_key_moments(
    background_tasks: BackgroundTasks,
    video: Video = Depends(get_owned_video),
    db: Session = Depends(get_db),
):
    """
    Generate key moments for a video owned by the current user.
    """
    transcript = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if not transcript or not transcript.segments:
        raise HTTPException(
            status_code=400,
            detail="Transcript segments not found. Cannot generate key moments.",
        )
    
    background_tasks.add_task(
        run_generate_key_moments,
        video.id,
        video.file_path,
        transcript.segments,
    )
    
    # Return existing key moments (could be empty, they will be replaced in background)
    return get_key_moments(video, db)



@router.get(
    "/{video_id}/key-moments",
    response_model=KeyMomentsResponse,
)
def get_key_moments(
    video: Video = Depends(get_owned_video),
    db: Session = Depends(get_db),
):
    """
    Return detected key moments for a video owned by the current user.
    """

    moments = (
        db.query(KeyMoment)
        .filter(KeyMoment.video_id == video.id)
        .order_by(KeyMoment.start_time)
        .all()
    )

    key_moments = []

    for moment in moments:
        highlight_url = None

        if moment.highlight_path:
            highlight_url = (
                f"/videos/{video.id}/highlights/{moment.id}"
            )

        key_moments.append(
            {
                "id": moment.id,
                "start_time": moment.start_time,
                "end_time": moment.end_time,
                "title": moment.title,
                "topic": moment.topic,
                "importance_score": moment.importance_score,
                "text": moment.text,
                "highlight_path": highlight_url,
            }
        )

    return {
        "video_id": video.id,
        "status": video.status,
        "key_moments": key_moments,
    }


@router.get(
    "/{video_id}/highlights/{moment_id}",
)
def get_highlight(
    moment_id: int,
    video: Video = Depends(get_owned_video),
    db: Session = Depends(get_db),
):
    """
    Serve the generated highlight video for a key moment.

    The video and key moment must belong to the authenticated user.
    """

    moment = (
        db.query(KeyMoment)
        .filter(
            KeyMoment.id == moment_id,
            KeyMoment.video_id == video.id,
        )
        .first()
    )

    if moment is None:
        raise HTTPException(
            status_code=404,
            detail="Key moment not found",
        )

    if not moment.highlight_path:
        raise HTTPException(
            status_code=404,
            detail="Highlight video is not available.",
        )

    highlight_path = Path(moment.highlight_path)

    if not highlight_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Highlight video file not found.",
        )

    return FileResponse(
        path=highlight_path,
        media_type="video/mp4",
        filename=highlight_path.name,
    )