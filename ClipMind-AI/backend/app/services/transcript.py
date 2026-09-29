"""Transcript generation and persistence workflow."""

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transcript, TranscriptStatus, Video, VideoProcessingStatus
from app.services.speech_to_text import transcribe
from app.services.video_processing import update_video_status


def generate_transcript(db: Session, video: Video, storage) -> Transcript:
    """Download the stored video, transcribe it, and persist the result."""

    if video.processing_status in {VideoProcessingStatus.UPLOADED, VideoProcessingStatus.FAILED}:
        update_video_status(db, video, VideoProcessingStatus.PROCESSING, "Transcript processing started.")

    transcript = video.transcript or Transcript(video_id=video.id)
    transcript.status = TranscriptStatus.PROCESSING
    transcript.error_message = None
    db.add(transcript)
    db.commit()
    db.refresh(transcript)

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=Path(video.filename).suffix, delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            storage.download_fileobj(video.storage_key, temporary_file)
            temporary_file.flush()
        result = transcribe(temporary_path)
        transcript.text = result["text"]
        transcript.segments = result["segments"]
        transcript.language = result["language"]
        transcript.status = TranscriptStatus.COMPLETED
        db.commit()
        if video.processing_status == VideoProcessingStatus.PROCESSING:
            update_video_status(db, video, VideoProcessingStatus.COMPLETED, "Transcript processing completed successfully.")
        db.refresh(transcript)
        return transcript
    except Exception as exc:
        logging.getLogger(__name__).exception("Transcript generation failed for video_id=%s", video.id)
        transcript.status = TranscriptStatus.FAILED
        transcript.error_message = str(exc)
        db.commit()
        if video.processing_status == VideoProcessingStatus.PROCESSING:
            update_video_status(db, video, VideoProcessingStatus.FAILED, str(exc))
        raise
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)