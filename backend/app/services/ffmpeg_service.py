import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


ExtractionStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class AudioExtractionResult:
    """Result of extracting Whisper-ready audio from a video file.

    ``error_message`` is intentionally a safe, high-level diagnostic. Callers
    should log any command stderr themselves if they need deeper diagnostics,
    rather than returning it through an API response.
    """

    status: ExtractionStatus
    audio_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def remove_output_file(output_file: Path) -> None:
    """Remove an incomplete output file without masking the original failure."""
    try:
        output_file.unlink(missing_ok=True)
    except OSError:
        pass


def extract_audio(video_path: str, audio_path: str) -> AudioExtractionResult:
    """Extract mono 16 kHz PCM WAV audio from a video for transcription.

    This deliberately has a separate contract from :func:`process_video` so
    the existing Module 1 video-transcoding flow remains unchanged.
    """

    input_file = Path(video_path)
    output_file = Path(audio_path)

    if not input_file.is_file():
        remove_output_file(output_file)
        return AudioExtractionResult(
            status="failed",
            error_code="input_not_found",
            error_message="The source video file does not exist.",
        )

    if output_file.suffix.lower() != ".wav":
        return AudioExtractionResult(
            status="failed",
            error_code="invalid_output_path",
            error_message="Audio extraction output must use a .wav path.",
        )

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        remove_output_file(output_file)
        return AudioExtractionResult(
            status="failed",
            error_code="output_directory_unavailable",
            error_message="Unable to prepare audio output storage.",
        )

    command = [
        "ffmpeg",
        "-nostdin",
        "-i",
        str(input_file),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        "-y",
        str(output_file),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        remove_output_file(output_file)
        return AudioExtractionResult(
            status="failed",
            error_code="ffmpeg_unavailable",
            error_message="Audio extraction could not start.",
        )

    if result.returncode != 0:
        remove_output_file(output_file)
        return AudioExtractionResult(
            status="failed",
            error_code="ffmpeg_failed",
            error_message="FFmpeg could not extract audio from the video.",
        )

    return AudioExtractionResult(
        status="completed",
        audio_path=str(output_file),
    )


def process_video(input_path: str, output_path: str) -> bool:
    """
    Process a video using FFmpeg.

    Converts video to H.264 video and AAC audio.

    Returns:
        True if processing succeeds.
        False if processing fails.
    """

    input_file = Path(input_path)
    output_file = Path(output_path)

    if not input_file.is_file():
        remove_output_file(output_file)
        return False

    output_file.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg",
        "-nostdin",
        "-i",
        str(input_file),
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-y",
        str(output_file),
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            return True

        remove_output_file(output_file)
        return False

    except (OSError, subprocess.SubprocessError):
        remove_output_file(output_file)
        return False
