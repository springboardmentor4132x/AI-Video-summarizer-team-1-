"""Lazy, database-free Whisper transcription service for Module 2."""

from dataclasses import dataclass
from functools import lru_cache
import importlib
import os
from pathlib import Path
from typing import Any, Literal


TranscriptionStatus = Literal["queued", "processing", "completed", "failed"]


@dataclass(frozen=True)
class TranscriptionResult:
    """A safe service result suitable for later API and processing adapters."""

    status: TranscriptionStatus
    text: str | None = None
    language: str | None = None
    segments: list[dict[str, Any]] | None = None
    error_code: str | None = None
    error_message: str | None = None


DEFAULT_WHISPER_MODEL = "base"


@lru_cache(maxsize=None)
def load_whisper_model(model_name: str):
    """Load a Whisper model only when transcription is first requested."""

    whisper = importlib.import_module("whisper")
    return whisper.load_model(model_name)


def transcribe_audio(
    audio_path: str,
    language_hint: str | None = None,
) -> TranscriptionResult:
    """Transcribe an existing audio file without performing database work.

    Model loading and any initial model-weight download are intentionally lazy.
    Exception details are reduced to safe diagnostics so callers do not expose
    stack traces or backend-command output to API users.
    """

    input_file = Path(audio_path)
    if not input_file.is_file():
        return TranscriptionResult(
            status="failed",
            error_code="audio_not_found",
            error_message="The audio file does not exist.",
        )

    model_name = os.getenv("WHISPER_MODEL", DEFAULT_WHISPER_MODEL).strip()
    if not model_name:
        model_name = DEFAULT_WHISPER_MODEL

    try:
        model = load_whisper_model(model_name)
    except Exception as exc:
        return TranscriptionResult(
            status="failed",
            error_code="model_load_failed",
            error_message=f"Whisper model could not be loaded ({type(exc).__name__}).",
        )

    options: dict[str, Any] = {}
    if language_hint:
        options["language"] = language_hint

    try:
        raw_result = model.transcribe(str(input_file), **options)
    except Exception as exc:
        return TranscriptionResult(
            status="failed",
            error_code="transcription_failed",
            error_message=f"Whisper transcription failed ({type(exc).__name__}).",
        )

    if not isinstance(raw_result, dict):
        return TranscriptionResult(
            status="failed",
            error_code="invalid_transcription_result",
            error_message="Whisper returned an unexpected transcription result.",
        )

    raw_segments = raw_result.get("segments", [])
    if not isinstance(raw_segments, list):
        raw_segments = []

    segments = [segment for segment in raw_segments if isinstance(segment, dict)]
    language = raw_result.get("language")

    return TranscriptionResult(
        status="completed",
        text=str(raw_result.get("text", "")),
        language=str(language) if language is not None else language_hint,
        segments=segments,
    )
