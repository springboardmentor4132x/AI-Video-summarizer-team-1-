"""Video upload routes."""

from pathlib import Path
from tempfile import NamedTemporaryFile, SpooledTemporaryFile
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload
from starlette.background import BackgroundTask

from app.auth.authorization import Permission, has_permission, require_any_permission
from app.auth.dependencies import CurrentUser
from app.config import settings
from app.database import get_db
from app.models import UploadHistory, UploadStatus, User, Video, VideoProcessingStatus, VideoSourceType
from app.schemas.video import (
    VideoListResponse,
    VideoStatusResponse,
    VideoStatusUpdateRequest,
    VideoUploadResponse,
    YouTubeVideoRequest,
    YouTubeVideoResponse,
)
from app.services.storage import CloudStorageError, LocalStorage, S3Storage, get_storage
from app.services.ffmpeg_processing import ProcessingError, convert_to_browser_mp4, process_video
from app.services.video_processing import get_video, update_video_status
from app.services.youtube_service import YouTubeDownloadError, download_youtube_video, validate_youtube_url


router = APIRouter(prefix="/videos", tags=["videos"])

ALLOWED_VIDEO_TYPES = {
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
CHUNK_SIZE = 1024 * 1024
STATUS_VIEW_PERMISSION = require_any_permission(
    Permission.MANAGE_UPLOADED_VIDEOS,
    Permission.MANAGE_EDUCATIONAL_CONTENT,
    Permission.MONITOR_PLATFORM_ACTIVITY,
)
LIST_PERMISSION = require_any_permission(
    Permission.MANAGE_UPLOADED_VIDEOS,
    Permission.MANAGE_EDUCATIONAL_CONTENT,
    Permission.VIEW_AVAILABLE_CONTENT,
    Permission.MONITOR_PLATFORM_ACTIVITY,
)


def _upload_error(detail: str, response_status: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=response_status, detail=detail)


def _can_view_video(user: User, video: Video) -> bool:
    if has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY):
        return True
    if has_permission(user, Permission.MANAGE_UPLOADED_VIDEOS) or has_permission(
        user, Permission.MANAGE_EDUCATIONAL_CONTENT
    ):
        return video.user_id == user.id
    return has_permission(user, Permission.VIEW_AVAILABLE_CONTENT) and video.processing_status == VideoProcessingStatus.COMPLETED


def _parse_range(range_header: str | None, file_size: int) -> tuple[int, int, int] | None:
    if not range_header or not range_header.startswith("bytes="):
        return None
    value = range_header[6:].split(",", 1)[0].strip()
    if "-" not in value:
        raise HTTPException(status_code=416, detail="Invalid media range")
    start_text, end_text = value.split("-", 1)
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else file_size - 1
        else:
            suffix_length = int(end_text)
            if suffix_length <= 0:
                raise ValueError
            start = max(0, file_size - suffix_length)
            end = file_size - 1
    except ValueError as exc:
        raise HTTPException(status_code=416, detail="Invalid media range") from exc
    if start < 0 or start >= file_size or end < start:
        raise HTTPException(status_code=416, detail="Requested media range is not satisfiable")
    end = min(end, file_size - 1)
    return start, end, end - start + 1


def _stream_file(path: Path, start: int, length: int):
    with path.open("rb") as fileobj:
        fileobj.seek(start)
        remaining = length
        while remaining:
            chunk = fileobj.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _cleanup_media_files(*paths: Path) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


@router.post(
    "/upload",
    response_model=VideoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_video(
    file: UploadFile = File(...),
    user: User = Depends(
        require_any_permission(Permission.UPLOAD_VIDEOS, Permission.UPLOAD_LECTURE_VIDEOS)
    ),
    db: Session = Depends(get_db),
    storage: LocalStorage | S3Storage = Depends(get_storage),
) -> VideoUploadResponse:
    """Validate, store, and register an authenticated user's video upload."""

    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    expected_mime_type = ALLOWED_VIDEO_TYPES.get(extension)
    if not filename or not expected_mime_type:
        raise _upload_error("Unsupported video file type or extension")
    if file.content_type != expected_mime_type:
        raise _upload_error("The file type does not match its extension")

    video_id = uuid4()
    prefix = settings.s3_prefix.strip("/")
    storage_key = f"{prefix}/{user.id}/{video_id}{extension}" if prefix else f"{user.id}/{video_id}{extension}"
    total_size = 0
    temporary_file = SpooledTemporaryFile(max_size=settings.max_video_size_bytes, mode="w+b")

    try:
        while chunk := await file.read(CHUNK_SIZE):
            total_size += len(chunk)
            if total_size > settings.max_video_size_bytes:
                raise _upload_error("Video exceeds the maximum allowed size", status.HTTP_413_CONTENT_TOO_LARGE)
            temporary_file.write(chunk)
        if total_size == 0:
            raise _upload_error("The uploaded video is empty")
        temporary_file.seek(0)
        storage.upload_fileobj(temporary_file, storage_key, expected_mime_type)
    except HTTPException:
        raise
    except CloudStorageError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Video could not be uploaded to cloud storage: {exc}",
        ) from exc
    finally:
        await file.close()
        temporary_file.close()

    video = Video(
        id=video_id,
        user_id=user.id,
        filename=filename,
        storage_key=storage_key,
        mime_type=expected_mime_type,
        file_size_bytes=total_size,
        processing_status=VideoProcessingStatus.UPLOADED,
    )
    history = UploadHistory(
        video_id=video_id,
        status=UploadStatus.UPLOADED,
        notes="Video upload accepted; AI processing has not started.",
    )
    db.add_all([video, history])
    try:
        db.commit()
        db.refresh(video)
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            storage.delete_object(storage_key)
        except CloudStorageError:
            pass
        raise HTTPException(status_code=500, detail="Video metadata could not be stored") from exc

    return VideoUploadResponse(
        id=video.id,
        filename=video.filename,
        mime_type=video.mime_type,
        file_size_bytes=video.file_size_bytes,
        processing_status=video.processing_status,
        source_type=video.source_type,
        source_url=video.source_url,
        uploaded_at=video.uploaded_at,
    )


@router.post(
    "/youtube",
    response_model=YouTubeVideoResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_youtube_video(
    payload: YouTubeVideoRequest,
    user: User = Depends(require_any_permission(Permission.UPLOAD_VIDEOS, Permission.UPLOAD_LECTURE_VIDEOS)),
    db: Session = Depends(get_db),
    storage: LocalStorage | S3Storage = Depends(get_storage),
) -> YouTubeVideoResponse:
    """Validate, download, store, and register a YouTube-backed video before transcript processing."""

    reference = validate_youtube_url(payload.youtube_url)
    video_id = uuid4()
    downloaded_video: Path | None = None
    playable_video: Path | None = None
    temp_dir: Path | None = None
    storage_key: str | None = None
    metadata_committed = False
    try:
        downloaded_video, _acquired_mime_type, _acquired_size = download_youtube_video(reference.normalized_url)
        temp_dir = downloaded_video.parent
        playable_video = convert_to_browser_mp4(downloaded_video)
        playable_size = playable_video.stat().st_size
        storage_key = f"youtube/{user.id}/{video_id}.mp4"
        with playable_video.open("rb") as playable_file:
            storage.upload_fileobj(playable_file, storage_key, "video/mp4")

        with SpooledTemporaryFile(max_size=settings.max_video_size_bytes, mode="w+b") as verification_file:
            storage.download_fileobj(storage_key, verification_file)
            verification_file.seek(0, 2)
            stored_size = verification_file.tell()
        if stored_size == 0:
            raise CloudStorageError("Downloaded YouTube video was written to storage but could not be read back")

        if stored_size != playable_size:
            raise CloudStorageError("Stored YouTube video size does not match the playable file size")

        video = Video(
            id=video_id,
            user_id=user.id,
            filename=f"youtube-{reference.video_id}.mp4",
            storage_key=storage_key,
            mime_type="video/mp4",
            file_size_bytes=playable_size,
            source_type=VideoSourceType.YOUTUBE,
            source_url=reference.normalized_url,
            processing_status=VideoProcessingStatus.UPLOADED,
        )
        history = UploadHistory(
            video_id=video_id,
            status=UploadStatus.UPLOADED,
            notes=f"YouTube video stored from {reference.normalized_url}; processing has not started.",
        )
        db.add_all([video, history])
        try:
            db.commit()
            db.refresh(video)
            metadata_committed = True
        except SQLAlchemyError as exc:
            db.rollback()
            try:
                storage.delete_object(storage_key)
            except CloudStorageError:
                pass
            raise HTTPException(status_code=500, detail="YouTube video metadata could not be stored") from exc
        return YouTubeVideoResponse(
            video_id=video.id,
            source_type=video.source_type,
            source_url=video.source_url or reference.normalized_url,
            status=video.processing_status,
        )
    except (CloudStorageError, OSError, ProcessingError, ValueError, YouTubeDownloadError) as exc:
        if storage_key is not None and not metadata_committed:
            try:
                storage.delete_object(storage_key)
            except CloudStorageError:
                pass
        if downloaded_video is not None:
            downloaded_video.unlink(missing_ok=True)
        if playable_video is not None:
            playable_video.unlink(missing_ok=True)
        if isinstance(exc, YouTubeDownloadError):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        raise HTTPException(status_code=422, detail="The YouTube video could not be stored as playable media.") from exc
    finally:
        if playable_video is not None:
            playable_video.unlink(missing_ok=True)
        if downloaded_video is not None:
            downloaded_video.unlink(missing_ok=True)
        if temp_dir is not None:
            try:
                temp_dir.rmdir()
            except OSError:
                pass


@router.get("/{video_id}/media")
def stream_video_media(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    storage: LocalStorage | S3Storage = Depends(get_storage),
    range_header: str | None = Header(default=None, alias="Range"),
) -> StreamingResponse:
    """Stream an authorized stored video with browser range support."""

    video = get_video(db, video_id)
    if not _can_view_video(user, video):
        raise HTTPException(status_code=403, detail="You do not have permission to access this video")

    temporary_file = NamedTemporaryFile(suffix=Path(video.filename).suffix, delete=False)
    temporary_path = Path(temporary_file.name)
    playable_path = temporary_path
    converted_path: Path | None = None
    try:
        storage.download_fileobj(video.storage_key, temporary_file)
        temporary_file.close()
        file_size = temporary_path.stat().st_size
        if file_size == 0:
            raise CloudStorageError("Video storage returned an empty file")
        if video.mime_type not in {"video/mp4", "video/webm"} or Path(video.filename).suffix.lower() not in {".mp4", ".webm"}:
            converted_path = convert_to_browser_mp4(temporary_path)
            playable_path = converted_path
            file_size = playable_path.stat().st_size
        requested_range = _parse_range(range_header, file_size)
        start, end, length = requested_range or (0, file_size - 1, file_size)
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": f'inline; filename="{Path(video.filename).name}"',
        }
        if requested_range:
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        return StreamingResponse(
            _stream_file(playable_path, start, length),
            status_code=206 if requested_range else 200,
            media_type="video/mp4" if converted_path is not None else video.mime_type,
            headers=headers,
            background=BackgroundTask(_cleanup_media_files, temporary_path, *( [converted_path] if converted_path is not None else [] )),
        )
    except HTTPException:
        temporary_file.close()
        _cleanup_media_files(temporary_path, *( [converted_path] if converted_path is not None else [] ))
        raise
    except (CloudStorageError, OSError, ProcessingError) as exc:
        temporary_file.close()
        _cleanup_media_files(temporary_path, *( [converted_path] if converted_path is not None else [] ))
        raise HTTPException(status_code=404, detail="Video media is not available") from exc


@router.get("/", response_model=list[VideoListResponse])
def list_videos(
    user: User = Depends(LIST_PERMISSION),
    db: Session = Depends(get_db),
    limit: int = Query(default=500, ge=1, le=2000),
) -> list[VideoListResponse]:
    """Return videos visible to the current role without exposing storage keys."""

    query = (
        select(Video)
        .options(joinedload(Video.owner))
        .order_by(Video.uploaded_at.desc())
        .limit(limit)
    )
    if has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY):
        pass
    elif has_permission(user, Permission.MANAGE_UPLOADED_VIDEOS) or has_permission(
        user, Permission.MANAGE_EDUCATIONAL_CONTENT
    ):
        query = query.where(Video.user_id == user.id)
    elif has_permission(user, Permission.VIEW_AVAILABLE_CONTENT):
        query = query.where(Video.processing_status == VideoProcessingStatus.COMPLETED)

    return [
        VideoListResponse(
            id=video.id,
            filename=video.filename,
            mime_type=video.mime_type,
            file_size_bytes=video.file_size_bytes,
            duration_seconds=video.duration_seconds,
            processing_status=video.processing_status,
            source_type=video.source_type,
            source_url=video.source_url,
            uploaded_at=video.uploaded_at,
            owner_id=video.user_id,
            owner_name=video.owner.full_name,
        )
        for video in db.scalars(query).all()
    ]


def _status_response(video: Video) -> VideoStatusResponse:
    latest_event = max(video.upload_history, key=lambda event: event.uploaded_at, default=None)
    return VideoStatusResponse(
        id=video.id,
        filename=video.filename,
        processing_status=video.processing_status,
        updated_at=video.updated_at,
        latest_note=latest_event.notes if latest_event else None,
    )


@router.get("/status", response_model=list[VideoStatusResponse])
def video_statuses(
    user: User = Depends(STATUS_VIEW_PERMISSION),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[VideoStatusResponse]:
    """Return current statuses for owned videos or all platform videos for admins."""

    query = (
        select(Video)
        .options(joinedload(Video.upload_history))
        .order_by(Video.updated_at.desc())
        .limit(limit)
    )
    if not has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY):
        query = query.where(Video.user_id == user.id)
    return [_status_response(video) for video in db.scalars(query).unique().all()]


@router.post("/{video_id}/process", response_model=VideoStatusResponse)
def process_video_endpoint(
    video_id: UUID,
    user: User = Depends(STATUS_VIEW_PERMISSION),
    db: Session = Depends(get_db),
    storage: LocalStorage | S3Storage = Depends(get_storage),
) -> VideoStatusResponse:
    """Run the basic FFmpeg pipeline for an authorized video."""

    video = get_video(db, video_id)
    is_administrator = has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY)
    if not is_administrator and video.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot process this video")
    try:
        process_video(db, video, storage)
    except ProcessingError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return _status_response(video)


@router.patch("/{video_id}/status", response_model=VideoStatusResponse)
def update_status(
    video_id: UUID,
    request: VideoStatusUpdateRequest,
    user: User = Depends(STATUS_VIEW_PERMISSION),
    db: Session = Depends(get_db),
) -> VideoStatusResponse:
    """Update a video lifecycle state and append a corresponding history event."""

    video = get_video(db, video_id)
    is_administrator = has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY)
    if not is_administrator and video.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot update this video")
    update_video_status(db, video, request.status, request.notes)
    return _status_response(video)


@router.delete("/{video_id}")
def delete_video(
    video_id: UUID,
    user: CurrentUser,
    db: Session = Depends(get_db),
    storage: LocalStorage | S3Storage = Depends(get_storage),
) -> dict[str, str]:
    """Delete a single uploaded video and its stored media object."""

    video = get_video(db, video_id)
    is_administrator = has_permission(user, Permission.MONITOR_PLATFORM_ACTIVITY)
    if not is_administrator and video.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this video",
        )

    try:
        storage.delete_object(video.storage_key)
    except CloudStorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Video storage could not be removed: {exc}",
        ) from exc

    try:
        if video.transcript is not None:
            db.delete(video.transcript)
        if video.summary is not None:
            db.delete(video.summary)
        for key_moment in video.key_moments:
            db.delete(key_moment)
        for history_entry in video.upload_history:
            db.delete(history_entry)
        db.delete(video)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        import traceback
        print(f"DEBUG: Delete failed with error: {type(exc).__name__}: {exc}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Video metadata could not be deleted: {str(exc)[:200]}",
        ) from exc

    return {"message": "Video deleted successfully", "video_id": str(video.id)}