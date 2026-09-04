import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.dependencies.auth import get_current_user
from app.models.transcript import Summary, SummaryStatus, Transcript, TranscriptStatus
from app.models.video import Video
from app.services.ffmpeg_service import extract_audio, process_video
from app.services.summary_service import generate_summary_from_transcript
from app.services.transcription_service import transcribe_audio

router = APIRouter(prefix="/videos", tags=["videos"])
logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
UPLOAD_DIR = BACKEND_DIR / "uploads"
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MAX_FILE_SIZE = 500 * 1024 * 1024


def remove_file(path: Path | str) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _transcript_payload(transcript: Transcript) -> dict:
    return {
        "id": transcript.id,
        "video_id": transcript.video_id,
        "text": transcript.text or "",
        "segments": transcript.segments or [],
        "language": transcript.language,
        "status": transcript.status.value if isinstance(transcript.status, TranscriptStatus) else str(transcript.status),
        "error_message": transcript.error_message,
        "created_at": transcript.created_at.isoformat() if transcript.created_at else None,
        "updated_at": transcript.updated_at.isoformat() if transcript.updated_at else None,
    }


def _summary_payload(summary: Summary) -> dict:
    to_use = summary.short_summary or summary.detailed_summary or ""
    transcript_id = summary.transcript_id
    return {
        "id": summary.id,
        "video_id": transcript_id,
        "content": to_use,
        "created_at": summary.created_at.isoformat() if summary.created_at else None,
        "updated_at": summary.updated_at.isoformat() if summary.updated_at else None,
    }


def process_video_background(video_id: int, input_path: str, output_path: str):
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video is None:
            return

        video.status = "processing"
        db.commit()

        if not process_video(input_path=input_path, output_path=output_path):
            video.status = "failed"
            db.commit()
            return

        audio_path = UPLOAD_DIR / f"{uuid4()}_transcription.wav"
        extraction = extract_audio(video_path=input_path, audio_path=str(audio_path))

        if extraction.status != "completed" or not extraction.audio_path:
            video.status = "failed"
            db.commit()
            return

        transcription = transcribe_audio(extraction.audio_path)
        if transcription.status != "completed":
            video.status = "failed"
            db.commit()
            return

        transcript = db.query(Transcript).filter(Transcript.video_id == video.id).first()
        if transcript is None:
            transcript = Transcript(video_id=video.id)
            db.add(transcript)

        transcript.text = transcription.text or ""
        transcript.language = transcription.language or "en"
        transcript.segments = transcription.segments or []
        transcript.status = TranscriptStatus.COMPLETED
        transcript.error_message = None
        db.flush()

        # summary is derived from the completed transcript, not the raw video
        summary = db.query(Summary).filter(Summary.transcript_id == transcript.id).first()
        if summary is None:
            summary = Summary(transcript_id=transcript.id)
            db.add(summary)
        summary.short_summary = generate_summary_from_transcript(transcript.text or "")
        summary.detailed_summary = transcript.text or ""
        summary.status = SummaryStatus.COMPLETED
        db.commit()
        video.status = "completed"
        db.commit()
    except Exception:
        db.rollback()
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.status = "failed"
                db.commit()
        except Exception:
            db.rollback()
    finally:
        remove_file(output_path)
        remove_file(str(UPLOAD_DIR / f"{video_id}_transcription.wav"))
        db.close()


@router.post("/upload", response_model=dict, status_code=status.HTTP_201_CREATED)
async def upload_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    extension = Path(file.filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported video format")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid4()}{extension}"
    input_path = UPLOAD_DIR / unique_name
    output_path = UPLOAD_DIR / f"{uuid4()}_processed.mp4"
    total_size = 0

    try:
        with input_path.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="Video file is too large")
                buffer.write(chunk)
    finally:
        await file.close()

    video = Video(
        user_id=current_user.id,
        filename=file.filename,
        file_path=str(input_path),
        status="uploaded",
    )

    db.add(video)
    db.flush()
    db.refresh(video)
    db.commit()

    background_tasks.add_task(process_video_background, video.id, str(input_path), str(output_path))
    return {"id": video.id, "filename": video.filename, "status": video.status}


@router.get("/{video_id}/transcript")
def get_transcript(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    transcript = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")

    return _transcript_payload(transcript)


@router.post("/{video_id}/transcript")
def generate_transcript(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    transcript = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if transcript is None:
        transcript = Transcript(video_id=video.id, status=TranscriptStatus.PROCESSING)
        db.add(transcript)
    else:
        transcript.status = TranscriptStatus.PROCESSING
        transcript.error_message = None

    db.commit()
    db.refresh(transcript)

    input_path = Path(video.file_path)
    audio_output_path = UPLOAD_DIR / f"{uuid4()}_transcription.wav"
    extraction = extract_audio(str(input_path), str(audio_output_path))
    if extraction.status == "completed":
        transcription = transcribe_audio(extraction.audio_path)
        if transcription.status == "completed":
            transcript.text = transcription.text or ""
            transcript.language = transcription.language or "en"
            transcript.segments = transcription.segments or []
            transcript.status = TranscriptStatus.COMPLETED
            transcript.error_message = None
            db.commit()
            db.refresh(transcript)
            return _transcript_payload(transcript)

            video.status = "failed"
            db.commit()
    transcript.status = TranscriptStatus.FAILED
    transcript.error_message = "Transcription failed."
    db.commit()
    db.refresh(transcript)
    return _transcript_payload(transcript)


@router.get("/{video_id}/summary")
def get_summary(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    transcript = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")

    if transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Transcript must be completed before summary generation")

    summary = db.query(Summary).filter(Summary.transcript_id == transcript.id).first()
    if summary is None:
        summary = Summary(
            transcript_id=transcript.id,
            short_summary=generate_summary_from_transcript(transcript.text or ""),
            detailed_summary=transcript.text or "",
            status=SummaryStatus.COMPLETED,
        )
        db.add(summary)
        db.commit()
        db.refresh(summary)

    return _summary_payload(summary)


@router.post("/{video_id}/summary")
def generate_summary(video_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    video = db.query(Video).filter(Video.id == video_id, Video.user_id == current_user.id).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")

    transcript = db.query(Transcript).filter(Transcript.video_id == video.id).first()
    if transcript is None:
        raise HTTPException(status_code=404, detail="Transcript not found")

    if transcript.status != TranscriptStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Transcript must be completed before summary generation")

    summary = db.query(Summary).filter(Summary.transcript_id == transcript.id).first()
    if summary is None:
        summary = Summary(transcript_id=transcript.id)
        db.add(summary)

    summary.short_summary = generate_summary_from_transcript(transcript.text or "")
    summary.detailed_summary = transcript.text or ""
    summary.status = SummaryStatus.COMPLETED
    db.commit()
    db.refresh(summary)
    return _summary_payload(summary)
