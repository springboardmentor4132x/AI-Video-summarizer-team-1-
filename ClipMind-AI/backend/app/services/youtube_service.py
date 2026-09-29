"""YouTube URL validation and authorized-source metadata handling."""

from __future__ import annotations

import re
import shutil
import socket
import tempfile
from dataclasses import dataclass
import logging
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from fastapi import HTTPException, status

import yt_dlp

from app.config import settings

logger = logging.getLogger(__name__)

YOUTUBE_HOSTS = {
    "www.youtube.com",
    "youtube.com",
    "m.youtube.com",
    "youtu.be",
    "www.youtu.be",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
}
VIDEO_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{11}")


@dataclass(frozen=True)
class YouTubeVideoReference:
    video_id: str
    normalized_url: str


class YouTubeDownloadError(RuntimeError):
    """Raised when a configured YouTube source cannot be fetched."""

    def __init__(self, message: str, *, code: str = "UNAVAILABLE") -> None:
        super().__init__(message)
        self.code = code


def _safe_error_detail(error: BaseException) -> str:
    """Keep diagnostics useful without logging credential-like values."""

    detail = str(error)
    detail = re.sub(r"(?i)(authorization|cookie|token|password|secret)\s*[:=]\s*\S+", r"\1=[REDACTED]", detail)
    return detail[:600]


def _classify_download_error(error: BaseException) -> tuple[str, str]:
    """Map yt-dlp failures to stable categories and safe user guidance."""

    detail = str(error)
    lowered = detail.lower()
    if "sign in to confirm" in lowered or "confirm you're not a bot" in lowered:
        return "BOT_VERIFICATION", "YouTube requires bot verification for this video. Use an authorized upload or provide an available transcript."
    if "login_required" in lowered or "sign in" in lowered:
        return "LOGIN_REQUIRED", "YouTube requires sign-in for this video. Use an authorized upload or provide an available transcript."
    if any(marker in lowered for marker in ("private video", "video unavailable", "video is unavailable", "not available")):
        return "VIDEO_UNAVAILABLE", "This YouTube video is private, deleted, restricted, or unavailable to the server. Check its visibility or use an authorized upload."
    if isinstance(error, (TimeoutError, socket.timeout)) or any(marker in lowered for marker in ("timed out", "timeout", "timedout")):
        return "NETWORK_TIMEOUT", "YouTube did not respond in time. Check the URL and try again later, or use an authorized upload."
    return "DOWNLOAD_FAILED", "YouTube could not provide this video to the server. Try again later or use an authorized upload."


def _is_supported_youtube_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    return hostname.rstrip(".").lower() in YOUTUBE_HOSTS


def extract_youtube_video_id(url: str) -> str:
    """Return the YouTube video ID, or raise a validation error."""

    candidate = (url or "").strip()
    if not candidate:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="YouTube URL is required")

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").lower().rstrip(".")

    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not _is_supported_youtube_host(hostname):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid YouTube URL")

    if hostname in {"youtu.be", "www.youtu.be"}:
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) == 1:
            return path_parts[0]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid YouTube URL")

    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) == 2 and path_parts[0].lower() in {"shorts", "embed"}:
        return path_parts[1]

    query_params = parse_qs(parsed.query)
    if path_parts == ["watch"] and query_params.get("v", [None])[0]:
        return query_params["v"][0]

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported YouTube URL")


def validate_youtube_url(url: str) -> YouTubeVideoReference:
    """Validate a YouTube URL and normalize it to a canonical reference."""

    video_id = extract_youtube_video_id(url)
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid YouTube URL")

    normalized = f"https://www.youtube.com/watch?v={video_id}"
    return YouTubeVideoReference(video_id=video_id, normalized_url=normalized)


def download_youtube_video(url: str) -> tuple[Path, str, int]:
    """Download a public YouTube media stream to a temporary file and return its path and metadata.

    The caller owns cleanup of the returned temporary directory after conversion/storage is complete.
    """

    reference = validate_youtube_url(url)
    temp_dir = Path(tempfile.mkdtemp(prefix="youtube-download-"))
    output_template = str(temp_dir / "clipmind-youtube.%(ext)s")
    options = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "socket_timeout": settings.youtube_socket_timeout_seconds,
        "retries": settings.youtube_max_retries,
        "fragment_retries": settings.youtube_fragment_retries,
        "extractor_retries": settings.youtube_max_retries,
        "max_filesize": settings.max_video_size_bytes,
        "match_filter": lambda info, *, incomplete: (
            "Video duration exceeds the maximum allowed length"
            if info.get("duration") and info["duration"] > settings.youtube_max_duration_seconds
            else None
        ),
    }
    if shutil.which("node"):
        options["js_runtimes"] = {"node": {}}
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([reference.normalized_url])
    except yt_dlp.utils.DownloadError as exc:
        if "javascript runtime" in str(exc).lower() or "no supported javascript" in str(exc).lower():
            code = "RUNTIME_UNAVAILABLE"
            message = "YouTube extraction is unavailable because the configured JavaScript runtime is missing."
        else:
            code, message = _classify_download_error(exc)
        logger.warning(
            "YouTube acquisition failed video_id=%s category=%s error_type=%s detail=%s",
            reference.video_id,
            code,
            type(exc).__name__,
            _safe_error_detail(exc),
        )
        raise YouTubeDownloadError(message, code=code) from exc
    except yt_dlp.utils.YoutubeDLError as exc:
        logger.exception(
            "Unexpected YouTube extractor error video_id=%s category=UNEXPECTED_INTERNAL error_type=%s detail=%s",
            reference.video_id,
            type(exc).__name__,
            _safe_error_detail(exc),
        )
        raise YouTubeDownloadError("The YouTube extractor failed unexpectedly. Try again later or use an authorized upload.", code="UNEXPECTED_INTERNAL") from exc

    candidates = sorted(temp_dir.glob("clipmind-youtube.*"), key=lambda path: path.stat().st_size, reverse=True)
    if not candidates:
        raise YouTubeDownloadError("YouTube download did not produce a video file")

    downloaded = candidates[0]
    if not downloaded.exists() or downloaded.stat().st_size == 0:
        raise YouTubeDownloadError("Downloaded YouTube video is empty")

    suffix = downloaded.suffix.lower()
    if suffix in {".webm", ".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac", ".m4v", ".mp4", ".mov", ".avi", ".mkv"}:
        mime_type = {
            ".webm": "audio/webm",
            ".m4a": "audio/mp4",
            ".mp3": "audio/mpeg",
            ".wav": "audio/wav",
            ".aac": "audio/aac",
            ".ogg": "audio/ogg",
            ".flac": "audio/flac",
            ".m4v": "video/x-m4v",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
        }[suffix]
    else:
        raise YouTubeDownloadError(f"Unsupported YouTube file type: {suffix or 'unknown'}")

    file_size = downloaded.stat().st_size
    logger.info(
        "YouTube acquisition completed for video_id=%s, suffix=%s, size_bytes=%d",
        reference.video_id,
        suffix,
        file_size,
    )
    return downloaded, mime_type, file_size


def get_permitted_youtube_metadata(url: str) -> dict[str, str | bool | None]:
    """Return metadata for an authorized YouTube source when retrieval is available."""

    reference = validate_youtube_url(url)
    return {
        "video_id": reference.video_id,
        "source_url": reference.normalized_url,
        "authorized": True,
        "retrieval_available": True,
        "reason": "Public YouTube content retrieval is enabled via the configured download mechanism.",
    }
