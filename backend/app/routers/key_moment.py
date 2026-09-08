from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.video import Video
from app.models.key_moment import KeyMoment
from app.schemas.key_moment import KeyMomentsResponse


router = APIRouter(
    prefix="/videos",
    tags=["key-moments"],
)


@router.get(
    "/{video_id}/key-moments",
    response_model=KeyMomentsResponse,
)
def get_key_moments(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return detected key moments for a video owned by the current user.
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

    moments = (
        db.query(KeyMoment)
        .filter(KeyMoment.video_id == video_id)
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
    video_id: int,
    moment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Serve the generated highlight video for a key moment.

    The video and key moment must belong to the authenticated user.
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

    moment = (
        db.query(KeyMoment)
        .filter(
            KeyMoment.id == moment_id,
            KeyMoment.video_id == video_id,
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