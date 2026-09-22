from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.video import get_owned_video
from app.models.video import Video
from app.schemas.transcript import TranscriptResponse


router = APIRouter(tags=["transcripts"])


def _get_transcript_from_video(video: Video):
    if video.transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return video.transcript


@router.get("/transcripts/{video_id}", response_model=TranscriptResponse)
def get_transcript(video: Video = Depends(get_owned_video)):
    return _get_transcript_from_video(video)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
def get_video_transcript(video: Video = Depends(get_owned_video)):
    return _get_transcript_from_video(video)