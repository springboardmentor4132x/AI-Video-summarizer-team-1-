import subprocess
from pathlib import Path


def remove_output_file(output_file: Path) -> None:
    """Remove an incomplete output file without masking the original failure."""
    try:
        output_file.unlink(missing_ok=True)
    except OSError:
        pass


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
