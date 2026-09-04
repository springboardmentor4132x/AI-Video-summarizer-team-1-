from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import subprocess
from typing import Any, Literal


HighlightStatus = Literal["completed", "failed"]


@dataclass(frozen=True)
class HighlightExtractionResult:
    """Result of extracting a video highlight clip.

    ``error_message`` is intentionally a safe, high-level diagnostic. Callers
    should log any command stderr themselves if they need deeper diagnostics,
    rather than returning it through an API response.
    """

    status: HighlightStatus
    highlight_path: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def remove_output_file(output_file: Path) -> None:
    """Remove an incomplete output file without masking the original failure."""
    try:
        output_file.unlink(missing_ok=True)
    except OSError:
        pass


def extract_highlight(
    video_path: str | Path,
    start_time: float,
    end_time: float,
    output_path: str | Path,
) -> HighlightExtractionResult:
    """Extract a video highlight clip between start_time and end_time using FFmpeg.

    Args:
        video_path: Path to the input video file.
        start_time: Start timestamp in seconds.
        end_time: End timestamp in seconds.
        output_path: Destination path for the extracted highlight clip.

    Returns:
        HighlightExtractionResult indicating success or failure.
    """

    input_file = Path(video_path)
    output_file = Path(output_path)

    if not input_file.is_file():
        remove_output_file(output_file)
        return HighlightExtractionResult(
            status="failed",
            error_code="input_not_found",
            error_message="The source video file does not exist.",
        )

    try:
        start_val = float(start_time)
        end_val = float(end_time)
    except (TypeError, ValueError):
        remove_output_file(output_file)
        return HighlightExtractionResult(
            status="failed",
            error_code="invalid_timestamps",
            error_message="Timestamps must be valid numeric values.",
        )

    if (
        math.isnan(start_val)
        or math.isinf(start_val)
        or math.isnan(end_val)
        or math.isinf(end_val)
        or start_val < 0
        or end_val <= start_val
    ):
        remove_output_file(output_file)
        return HighlightExtractionResult(
            status="failed",
            error_code="invalid_timestamps",
            error_message="Invalid start or end timestamp.",
        )

    duration = end_val - start_val

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        remove_output_file(output_file)
        return HighlightExtractionResult(
            status="failed",
            error_code="output_directory_unavailable",
            error_message="Unable to prepare highlight output storage.",
        )

    command = [
        "ffmpeg",
        "-nostdin",
        "-ss",
        str(start_val),
        "-i",
        str(input_file),
        "-t",
        str(duration),
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
    except (OSError, subprocess.SubprocessError):
        remove_output_file(output_file)
        return HighlightExtractionResult(
            status="failed",
            error_code="ffmpeg_unavailable",
            error_message="Highlight extraction could not start.",
        )

    if result.returncode != 0:
        remove_output_file(output_file)
        return HighlightExtractionResult(
            status="failed",
            error_code="ffmpeg_failed",
            error_message="FFmpeg could not extract highlight from the video.",
        )

    return HighlightExtractionResult(
        status="completed",
        highlight_path=str(output_file),
    )


def extract_highlights_for_key_moments(
    video_path: str | Path,
    moments: list[Any],
    output_dir: str | Path,
) -> list[HighlightExtractionResult]:
    """Extract video highlight clips for a list of detected key moments.

    Args:
        video_path: Path to the input video file.
        moments: List of KeyMoment objects or dicts containing start_time/end_time.
        output_dir: Directory where highlight clips should be saved.

    Returns:
        List of HighlightExtractionResult for each extracted moment.
    """

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    results: list[HighlightExtractionResult] = []

    for idx, moment in enumerate(moments, start=1):
        start = getattr(moment, "start_time", None)
        if start is None and isinstance(moment, dict):
            start = moment.get("start_time", moment.get("start"))

        end = getattr(moment, "end_time", None)
        if end is None and isinstance(moment, dict):
            end = moment.get("end_time", moment.get("end"))

        if start is None or end is None:
            results.append(
                HighlightExtractionResult(
                    status="failed",
                    error_code="invalid_timestamps",
                    error_message="Timestamps must be valid numeric values.",
                )
            )
            continue

        clip_name = f"highlight_{idx}_{int(float(start))}_{int(float(end))}.mp4"
        clip_path = out_dir / clip_name

        res = extract_highlight(
            video_path=video_path,
            start_time=float(start),
            end_time=float(end),
            output_path=clip_path,
        )
        results.append(res)

    return results
