"""Protected key moment detection routes."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.auth.dependencies import CurrentUser
from app.database import get_db
from app.models import KeyMoment, TranscriptStatus, Video
from app.schemas.key_moment import KeyMomentResponse
from app.services.key_moments import KeyMomentError, detect_key_moments

router = APIRouter(prefix="/videos", tags=["key moments"])


def _get_owned_video(db: Session, video_id: UUID, user_id: UUID) -> Video:
    video = db.scalar(
        select(Video)
        .options(joinedload(Video.transcript), joinedload(Video.key_moments))
        .where(Video.id == video_id)
    )
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    if video.user_id != user_id:
        raise HTTPException(status_code=403, detail="You do not have permission to access this video")
    return video


@router.post("/{video_id}/key-moments", response_model=list[KeyMomentResponse])
@router.post("/{video_id}/key-moments/generate", response_model=list[KeyMomentResponse])
def generate_key_moments(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)) -> list[KeyMomentResponse]:
    video = _get_owned_video(db, video_id, user.id)
    if video.transcript is None or video.transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=404, detail="Generate the transcript first before detecting key moments.")
    try:
        moments = detect_key_moments(video.transcript)
    except KeyMomentError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.execute(delete(KeyMoment).where(KeyMoment.video_id == video.id))
    db.add_all(moments)
    db.commit()
    for moment in moments:
        db.refresh(moment)
    return [KeyMomentResponse.model_validate(moment) for moment in moments]


@router.get("/{video_id}/key-moments", response_model=list[KeyMomentResponse])
def get_key_moments(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)) -> list[KeyMomentResponse]:
    video = _get_owned_video(db, video_id, user.id)
    moments = db.scalars(
        select(KeyMoment).where(KeyMoment.video_id == video.id).order_by(KeyMoment.start_time)
    ).all()
    return [KeyMomentResponse.model_validate(moment) for moment in moments]


@router.delete("/{video_id}/key-moments", status_code=status.HTTP_204_NO_CONTENT)
def delete_key_moments(video_id: UUID, user: CurrentUser, db: Session = Depends(get_db)) -> Response:
    video = _get_owned_video(db, video_id, user.id)
    db.execute(delete(KeyMoment).where(KeyMoment.video_id == video.id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
