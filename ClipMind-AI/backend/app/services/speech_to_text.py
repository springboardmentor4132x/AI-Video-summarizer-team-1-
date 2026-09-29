"""Speech-to-text provider boundary for local/demo transcription."""

import logging
import subprocess
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from app.config import settings


logger = logging.getLogger(__name__)


class SpeechToTextError(Exception):
    """Raised when transcription cannot be completed."""


@lru_cache(maxsize=1)
def load_whisper_model():
    """Load the configured Whisper model once and reuse it across requests."""
    try:
        import whisper
    except ImportError as exc:
        raise SpeechToTextError(
            "Speech-to-text service is not configured. Install openai-whisper and its dependencies."
        ) from exc
    return whisper.load_model(settings.whisper_model)


def _extract_audio(video_path: Path) -> Path:
    """Convert a video into a WAV file for Whisper so varied input formats are handled reliably."""
    suffix = ".wav"
    temp_audio = NamedTemporaryFile(suffix=suffix, delete=False)
    temp_audio.close()
    audio_path = Path(temp_audio.name)
    command = [
        settings.ffmpeg_binary,
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=settings.ffmpeg_timeout_seconds, check=False)
    if result.returncode != 0:
        audio_path.unlink(missing_ok=True)
        raise SpeechToTextError(f"Audio extraction failed: {result.stderr.strip() or 'ffmpeg returned an error'}")
    return audio_path


def transcribe(video_path: Path) -> dict[str, Any]:
    """Transcribe a video with the locally installed Whisper provider."""
    if not video_path.exists():
        raise SpeechToTextError("Video file could not be found.")

    audio_path = video_path
    should_cleanup = False
    if video_path.suffix.lower() not in {".wav", ".mp3", ".flac", ".m4a", ".aac"}:
        audio_path = _extract_audio(video_path)
        should_cleanup = True

    try:
        model = load_whisper_model()
        options: dict[str, Any] = {"fp16": False}
        if settings.whisper_language:
            options["language"] = settings.whisper_language
        result = model.transcribe(str(audio_path), **options)
    except Exception as exc:
        logger.exception("Speech-to-text processing failed for %s", video_path)
        raise SpeechToTextError(f"Transcript generation failed: {exc}") from exc
    finally:
        if should_cleanup and audio_path.exists():
            audio_path.unlink(missing_ok=True)

    segments = [
        {
            "start_time": float(segment.get("start", 0.0)),
            "end_time": float(segment.get("end", 0.0)),
            "text": str(segment.get("text", "")).strip(),
        }
        for segment in result.get("segments", [])
    ]
    text = str(result.get("text", "")).strip()
    if not text:
        raise SpeechToTextError("Transcript generation failed: no speech was detected")
    return {"text": text, "segments": segments, "language": result.get("language")}