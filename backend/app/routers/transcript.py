from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.transcript import Transcript
from app.models.video import Video
from app.schemas.transcript import TranscriptResponse


router = APIRouter(prefix="/videos", tags=["transcripts"])


@router.get("/{video_id}/transcript", response_model=TranscriptResponse)
def get_transcript(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    transcript = (
        db.query(Transcript)
        .join(Video, Transcript.video_id == Video.id)
        .filter(Video.id == video_id, Video.user_id == current_user.id)
        .first()
    )
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return transcript
