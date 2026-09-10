from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.video import get_owned_video
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import TranscriptStatus
from app.models.video import Video
from app.schemas.summary import SummaryResponse
from app.services.summarization_service import summarize_transcript


router = APIRouter(tags=["summaries"])


def _get_summary(video: Video) -> Summary:
    if video.transcript is None or video.transcript.summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return video.transcript.summary


@router.get("/summaries/{video_id}", response_model=SummaryResponse)
@router.get("/videos/{video_id}/summary", response_model=SummaryResponse)
def get_summary(video: Video = Depends(get_owned_video)):
    return _get_summary(video)


def _generate_summary(video: Video, db: Session, regenerate: bool = False) -> Summary:
    transcript = video.transcript
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    if transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=409, detail="Transcript must be completed before summarization")

    summary = transcript.summary
    if summary is None:
        summary = Summary(transcript_id=transcript.id, status=SummaryStatus.NOT_STARTED)
        db.add(summary)
        db.flush()

    if summary.status == SummaryStatus.PROCESSING:
        raise HTTPException(status_code=409, detail="Summary generation is already in progress")
    if summary.status == SummaryStatus.COMPLETED and not regenerate:
        return summary

    summary.status = SummaryStatus.PROCESSING
    db.commit()
    try:
        result = summarize_transcript(transcript)
        summary.short_summary = result.short_summary
        summary.detailed_summary = result.detailed_summary
        summary.status = SummaryStatus.COMPLETED
        db.commit()
        db.refresh(summary)
        return summary
    except Exception as exc:
        db.rollback()
        failed_summary = db.query(Summary).filter(Summary.id == summary.id).first()
        if failed_summary is not None:
            failed_summary.status = SummaryStatus.FAILED
            db.commit()
        raise HTTPException(status_code=500, detail="Summary generation failed") from exc


@router.post("/summaries/{video_id}/generate", response_model=SummaryResponse, status_code=status.HTTP_200_OK)
@router.post("/videos/{video_id}/summary", response_model=SummaryResponse, status_code=status.HTTP_200_OK)
def generate_summary(video: Video = Depends(get_owned_video), db: Session = Depends(get_db)):
    return _generate_summary(video, db)


@router.post("/videos/{video_id}/summary/regenerate", response_model=SummaryResponse)
def regenerate_summary(video: Video = Depends(get_owned_video), db: Session = Depends(get_db)):
    return _generate_summary(video, db, regenerate=True)