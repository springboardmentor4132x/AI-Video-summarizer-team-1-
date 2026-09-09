from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.transcript import Transcript
from app.models.video import Video
from app.schemas.transcript import TranscriptResponse


router = APIRouter(tags=["transcripts"])


def _get_owned_transcript(video_id: int, db: Session, current_user):
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None or video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return video.transcript


@router.get("/transcripts/{video_id}", response_model=TranscriptResponse)
def get_transcript(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return _get_owned_transcript(video_id, db, current_user)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def get_video_transcript(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    return _get_owned_transcript(video_id, db, current_user)