import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies.auth import get_current_user
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import Transcript, TranscriptStatus
from app.models.video import Video
from app.schemas.summary import SummaryResponse
from app.services.summarization_service import summarize_text


router = APIRouter(prefix="/videos", tags=["summaries"])
logger = logging.getLogger(__name__)


def _owned_transcript(video_id: UUID, current_user, db: Session) -> Transcript:
    transcript = (
        db.query(Transcript)
        .join(Video, Transcript.video_id == Video.id)
        .filter(Video.id == video_id, Video.user_id == current_user.id)
        .first()
    )
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return transcript


def _get_summary(video_id: UUID, current_user, db: Session) -> Summary:
    transcript = _owned_transcript(video_id, current_user, db)
    summary = db.query(Summary).filter(Summary.transcript_id == transcript.id).first()
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    return summary


@router.get("/{video_id}/summary", response_model=SummaryResponse)
def get_summary(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _get_summary(video_id, current_user, db)


@router.post("/{video_id}/summary", response_model=SummaryResponse)
def generate_summary(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    transcript = _owned_transcript(video_id, current_user, db)
    if transcript.status != TranscriptStatus.COMPLETED or not transcript.text:
        raise HTTPException(status_code=409, detail="Transcript is not completed")

    summary = (
        db.query(Summary)
        .filter(Summary.transcript_id == transcript.id)
        .with_for_update()
        .first()
    )
    if summary is None:
        summary = Summary(transcript_id=transcript.id, status=SummaryStatus.NOT_STARTED)
        db.add(summary)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            summary = (
                db.query(Summary)
                .filter(Summary.transcript_id == transcript.id)
                .with_for_update()
                .one()
            )

    if summary.status == SummaryStatus.PROCESSING:
        db.rollback()
        raise HTTPException(status_code=409, detail="Summary generation is already in progress")
    if summary.status == SummaryStatus.COMPLETED:
        return summary

    summary.status = SummaryStatus.PROCESSING
    db.commit()
    db.refresh(summary)

    try:
        result = summarize_text(transcript.text)
        summary.short_summary = result.short_summary
        summary.detailed_summary = result.detailed_summary
        summary.status = SummaryStatus.COMPLETED
        db.commit()
        db.refresh(summary)
        return summary
    except Exception:
        logger.exception("Summary generation failed for transcript %s", transcript.id)
        db.rollback()
        summary = db.query(Summary).filter(Summary.transcript_id == transcript.id).one()
        summary.status = SummaryStatus.FAILED
        db.commit()
        raise HTTPException(status_code=500, detail="Summary generation failed")


@router.post("/{video_id}/summary/retry", response_model=SummaryResponse)
def retry_summary(
    video_id: UUID,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    transcript = _owned_transcript(video_id, current_user, db)
    summary = db.query(Summary).filter(Summary.transcript_id == transcript.id).first()
    if summary is None:
        raise HTTPException(status_code=404, detail="Summary not found")
    if summary.status != SummaryStatus.FAILED:
        raise HTTPException(status_code=409, detail="Only failed summaries can be retried")
    return generate_summary(video_id, db, current_user)
