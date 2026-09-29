"""FFmpeg-based technical video processing."""

import json
import logging
import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Protocol

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Video, VideoProcessingStatus
from app.services.storage import CloudStorageError, LocalStorage, S3Storage
from app.services.video_processing import update_video_status


logger = logging.getLogger(__name__)


class ProcessingError(Exception):
    """Raised when FFmpeg cannot process a video."""


class DownloadableStorage(Protocol):
    def download_fileobj(self, storage_key: str, fileobj) -> None: ...


class ProcessingResult:
    """Technical metadata extracted from a successfully processed video."""

    def __init__(self, duration_seconds: int | None) -> None:
        self.duration_seconds = duration_seconds


def _has_video_stream(input_path: Path) -> bool:
    suffix = input_path.suffix.lower()
    if suffix in {".mp4", ".mkv", ".mov", ".avi", ".m4v"}:
        return True
    if suffix in {".webm", ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}:
        return False

    result = _run_command(
        [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=index",
            "-of",
            "json",
            str(input_path),
        ]
    )
    if result.returncode != 0:
        return False
    try:
        streams = json.loads(result.stdout).get("streams", [])
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return bool(streams)


def convert_to_browser_mp4(input_path: Path) -> Path:
    """Transcode a source video or audio stream to an H.264/AAC MP4 for browser playback."""

    output_file = NamedTemporaryFile(suffix=".mp4", delete=False)
    output_path = Path(output_file.name)
    output_file.close()

    is_audio_only = not _has_video_stream(input_path)
    duration_seconds = 1
    if is_audio_only:
        try:
            duration_seconds = _extract_duration(input_path) or 1
        except ProcessingError:
            logger.warning("FFprobe duration metadata unavailable for %s; falling back to a 1-second silent video shell.", input_path)
            duration_seconds = 1
    if not is_audio_only:
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    else:
        command = [
            settings.ffmpeg_binary,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=black:s=1280x720:d={max(1, duration_seconds)}",
            "-i",
            str(input_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    try:
        result = _run_command(command)
        if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            detail = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "unknown FFmpeg error"
            raise ProcessingError(f"FFmpeg could not create a browser-compatible MP4: {detail}")
        return output_path
    except (OSError, ProcessingError, subprocess.SubprocessError):
        output_path.unlink(missing_ok=True)
        raise


def _run_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=settings.ffmpeg_timeout_seconds,
        check=False,
    )


def _extract_duration(video_path: Path) -> int | None:
    result = _run_command(
        [
            settings.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    if result.returncode != 0:
        raise ProcessingError("FFprobe could not read the video metadata")
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProcessingError("FFprobe returned invalid duration metadata") from exc
    return max(0, round(duration))


def _validate_with_ffmpeg(video_path: Path) -> None:
    result = _run_command(
        [settings.ffmpeg_binary, "-v", "error", "-i", str(video_path), "-f", "null", "-"]
    )
    if result.returncode != 0:
        raise ProcessingError("FFmpeg rejected the video")


def process_video(
    db: Session,
    video: Video,
    storage: DownloadableStorage | LocalStorage | S3Storage,
) -> ProcessingResult:
    """Download, inspect, and validate a cloud video, updating lifecycle state."""

    if video.processing_status not in {
        VideoProcessingStatus.UPLOADED,
        VideoProcessingStatus.FAILED,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Video cannot be processed from status {video.processing_status}",
        )
    logger.info("Starting FFmpeg processing for video_id=%s", video.id)
    update_video_status(db, video, VideoProcessingStatus.PROCESSING, "FFmpeg processing started.")

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(suffix=Path(video.filename).suffix, delete=False) as temporary_file:
            temporary_path = Path(temporary_file.name)
            storage.download_fileobj(video.storage_key, temporary_file)
            temporary_file.flush()
        duration_seconds = _extract_duration(temporary_path)
        _validate_with_ffmpeg(temporary_path)

        video.duration_seconds = duration_seconds
        update_video_status(
            db,
            video,
            VideoProcessingStatus.COMPLETED,
            "FFmpeg processing completed successfully.",
        )
        logger.info("Completed FFmpeg processing for video_id=%s", video.id)
        return ProcessingResult(duration_seconds)
    except (CloudStorageError, OSError, ProcessingError, subprocess.SubprocessError) as exc:
        logger.exception("FFmpeg processing failed for video_id=%s", video.id)
        update_video_status(db, video, VideoProcessingStatus.FAILED, str(exc))
        raise ProcessingError("Video processing failed") from exc
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
