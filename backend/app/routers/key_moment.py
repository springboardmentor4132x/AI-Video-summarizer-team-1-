from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user, require_role
from app.dependencies.video_access import learner_has_shared_access
from app.schemas.user import UserRole
from app.models.transcript import TranscriptStatus
from app.models.video import Video
from app.models.key_moment import KeyMoment
from app.schemas.key_moment import KeyMomentsResponse
from app.services.key_moment_service import detect_key_moments, save_key_moments, segment_topics


BACKEND_DIR = Path(__file__).resolve().parents[2]
HIGHLIGHTS_DIR = (BACKEND_DIR / "uploads" / "highlights").resolve()


router = APIRouter(
    prefix="/videos",
    tags=["key-moments"],
)


def get_owned_video(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
) -> Video:
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    return video


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
    if video is None and current_user.role.title() == UserRole.LEARNER.value and learner_has_shared_access(db, video_id, current_user.id):
        video = db.query(Video).filter(Video.id == video_id, Video.status == "completed").first()

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


@router.get("/{video_id}/topics")
def get_video_topics(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Return coherent transcript-backed topic regions and their evidence."""
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None and current_user.role.title() == UserRole.LEARNER.value and learner_has_shared_access(db, video_id, current_user.id):
        video = db.query(Video).filter(Video.id == video_id, Video.status == "completed").first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    transcript = video.transcript
    if transcript is None or transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="A completed transcript is required for topic segmentation")

    moments = db.query(KeyMoment).filter(KeyMoment.video_id == video.id).all()
    topics = segment_topics(transcript.segments or [])
    for topic in topics:
        related = [moment for moment in moments if moment.start_time < topic["end"] and moment.end_time > topic["start"]]
        topic["key_moment_count"] = len(related)
        topic["average_importance"] = round(sum(moment.importance_score for moment in related) / len(related), 3) if related else None
    return {"video_id": video.id, "topics": topics}


@router.post(
    "/{video_id}/key-moments/generate",
    response_model=KeyMomentsResponse,
)
def generate_key_moments(
    video_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(require_role([UserRole.CONTENT_CREATOR, UserRole.EDUCATOR])),
):
    """Regenerate key moments from the already stored transcript."""
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    transcript = video.transcript
    if transcript is None or transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Transcript must be completed before key-moment detection")
    moments = detect_key_moments(transcript.segments or [])
    saved = save_key_moments(db, video.id, moments)
    db.commit()
    return {
        "video_id": video.id,
        "status": video.status,
        "key_moments": saved,
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

    try:
        resolved_path = highlight_path.resolve(strict=False)
        resolved_path.relative_to(HIGHLIGHTS_DIR)
    except (OSError, ValueError):
        raise HTTPException(
            status_code=404,
            detail="Highlight video file not found.",
        )

    if not resolved_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Highlight video file not found.",
        )

    return FileResponse(
        path=resolved_path,
        media_type="video/mp4",
        filename=resolved_path.name,
    )
