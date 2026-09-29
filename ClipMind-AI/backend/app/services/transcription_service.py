"""Background transcription workflow for uploaded videos."""

from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Thread
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import Transcript, TranscriptStatus, Video
from app.services.speech_to_text import SpeechToTextError, transcribe
from app.services.storage import CloudStorageError, LocalStorage, S3Storage, get_storage

logger = logging.getLogger(__name__)


def _load_video(db: Session, video_id: UUID) -> Video | None:
    return db.scalar(select(Video).where(Video.id == video_id))


def _set_processing(db: Session, transcript: Transcript) -> Transcript:
    transcript.status = TranscriptStatus.PROCESSING
    transcript.error_message = None
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    return transcript


def _finish_success(db: Session, transcript: Transcript, text: str, segments: list[dict], language: str | None) -> Transcript:
    transcript.text = text
    transcript.segments = segments
    transcript.language = language
    transcript.status = TranscriptStatus.COMPLETED
    transcript.error_message = None
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    return transcript


def _finish_failure(db: Session, transcript: Transcript, exc: Exception) -> Transcript:
    transcript.status = TranscriptStatus.FAILED
    transcript.error_message = str(exc)
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    return transcript


def transcribe_video_record(video: Video, storage: LocalStorage | S3Storage) -> Transcript:
    """Synchronously transcribe a single video and persist the transcript result."""
    db = SessionLocal()
    try:
        transcript = video.transcript or Transcript(video_id=video.id)
        _set_processing(db, transcript)

        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(suffix=Path(video.filename).suffix or ".mp4", delete=False) as temporary_file:
                temporary_path = Path(temporary_file.name)
                storage.download_fileobj(video.storage_key, temporary_file)
                temporary_file.flush()

            result = transcribe(temporary_path)
            return _finish_success(
                db,
                transcript,
                str(result.get("text", "")).strip(),
                list(result.get("segments", [])),
                result.get("language"),
            )
        except Exception as exc:
            logger.exception("Transcript generation failed for video_id=%s", video.id)
            return _finish_failure(db, transcript, exc)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
    finally:
        db.close()


def start_background_transcription(video_id: UUID) -> Transcript:
    """Create or update the transcript record with PROCESSING and run the real transcription in a daemon thread."""
    db = SessionLocal()
    try:
        video = _load_video(db, video_id)
        if video is None:
            raise ValueError(f"Video {video_id} does not exist")

        transcript = video.transcript or Transcript(video_id=video.id)
        transcript.status = TranscriptStatus.PROCESSING
        transcript.error_message = None
        db.add(transcript)
        db.commit()
        db.refresh(transcript)
    finally:
        db.close()

    def _job() -> None:
        worker_db = SessionLocal()
        try:
            worker_video = _load_video(worker_db, video_id)
            if worker_video is None:
                logger.error("Transcript background job could not find video_id=%s", video_id)
                return
            storage = get_storage()
            try:
                transcribe_video_record(worker_video, storage)
            except (CloudStorageError, OSError, SpeechToTextError, ValueError) as exc:
                logger.exception("Background transcription failed for video_id=%s", video_id)
                transcript_record = worker_video.transcript or Transcript(video_id=worker_video.id)
                transcript_record.status = TranscriptStatus.FAILED
                transcript_record.error_message = str(exc)
                worker_db.add(transcript_record)
                worker_db.commit()
                worker_db.refresh(transcript_record)
        finally:
            worker_db.close()

    thread = Thread(target=_job, daemon=True, name=f"transcription-{video_id}")
    thread.start()
    return transcript
