from collections.abc import Generator
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID, uuid4

import pytest
import yt_dlp
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import UploadHistory, UploadStatus, Video, VideoProcessingStatus
from app.services.storage import CloudStorageError, get_storage
from app.services.youtube_service import YouTubeDownloadError, _classify_download_error, validate_youtube_url


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
client = TestClient(app)


class FakeStorage:
    def __init__(self) -> None:
        self.uploaded: dict[str, bytes] = {}
        self.deleted: list[str] = []
        self.fail_upload = False

    def upload_fileobj(self, fileobj, storage_key: str, mime_type: str) -> None:
        if self.fail_upload:
            raise CloudStorageError("simulated cloud failure")
        self.uploaded[storage_key] = fileobj.read()

    def delete_object(self, storage_key: str) -> None:
        self.deleted.append(storage_key)
        self.uploaded.pop(storage_key, None)

    def download_fileobj(self, storage_key: str, fileobj) -> None:
        fileobj.write(self.uploaded[storage_key])


fake_storage = FakeStorage()


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    fake_storage.uploaded.clear()
    fake_storage.deleted.clear()
    fake_storage.fail_upload = False
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: fake_storage
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)


def create_user(role: str) -> str:
    email = f"{role.lower().replace(' ', '-')}-{uuid4()}@example.com"
    registration = client.post(
        "/auth/register",
        json={
            "full_name": f"Test {role}",
            "email": email,
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": role,
        },
    )
    assert registration.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": email, "password": "strong-password"},
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def upload(token: str, filename: str, content: bytes, mime_type: str):
    return client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, content, mime_type)},
    )


def delete_video(token: str, video_id: str):
    return client.delete(
        f"/videos/{video_id}",
        headers={"Authorization": f"Bearer {token}"},
    )


def test_creator_upload_persists_owned_video_and_initial_history() -> None:
    token = create_user("Content Creator")

    response = upload(token, "lesson.mp4", b"video-bytes", "video/mp4")

    assert response.status_code == 201
    payload = response.json()
    assert payload["filename"] == "lesson.mp4"
    assert payload["mime_type"] == "video/mp4"
    assert payload["file_size_bytes"] == len(b"video-bytes")
    assert payload["processing_status"] == VideoProcessingStatus.UPLOADED

    with TestingSessionLocal() as db:
        video = db.scalar(select(Video).where(Video.filename == "lesson.mp4"))
        assert video is not None
        assert video.user_id
        assert video.processing_status == VideoProcessingStatus.UPLOADED
        history = db.scalar(select(UploadHistory).where(UploadHistory.video_id == video.id))
        assert history is not None
        assert history.status == UploadStatus.UPLOADED
        assert video.storage_key in fake_storage.uploaded
        assert fake_storage.uploaded[video.storage_key] == b"video-bytes"

    def test_authorized_media_endpoint_supports_ranges_and_preserves_mime_type() -> None:
        token = create_user("Content Creator")
        response = upload(token, "lesson.mp4", b"0123456789", "video/mp4")
        video_id = response.json()["id"]

        full_response = client.get(f"/videos/{video_id}/media", headers={"Authorization": f"Bearer {token}"})
        ranged_response = client.get(
            f"/videos/{video_id}/media",
            headers={"Authorization": f"Bearer {token}", "Range": "bytes=2-5"},
        )

        assert full_response.status_code == 200
        assert full_response.headers["content-type"] == "video/mp4"
        assert full_response.headers["accept-ranges"] == "bytes"
        assert full_response.content == b"0123456789"
        assert ranged_response.status_code == 206
        assert ranged_response.headers["content-range"] == "bytes 2-5/10"
        assert ranged_response.content == b"2345"


    def test_media_endpoint_preserves_video_authorization() -> None:
        creator_token = create_user("Content Creator")
        learner_token = create_user("Learner")
        response = upload(creator_token, "lesson.mp4", b"video-bytes", "video/mp4")
        video_id = response.json()["id"]

        denied = client.get(f"/videos/{video_id}/media", headers={"Authorization": f"Bearer {learner_token}"})

        assert denied.status_code == 403


def test_upload_rejects_invalid_extension_and_empty_file() -> None:
    token = create_user("Educator")

    invalid_type = upload(token, "lesson.txt", b"not video", "text/plain")
    empty = upload(token, "empty.mp4", b"", "video/mp4")

    assert invalid_type.status_code == 400
    assert "extension" in invalid_type.json()["detail"]
    assert empty.status_code == 400
    assert "empty" in empty.json()["detail"]


def test_upload_rejects_files_over_configured_limit(monkeypatch) -> None:
    monkeypatch.setattr(settings, "max_video_size_bytes", 4)
    token = create_user("Content Creator")

    response = upload(token, "large.mp4", b"12345", "video/mp4")

    assert response.status_code == 413
    assert "maximum allowed size" in response.json()["detail"]
    assert not fake_storage.uploaded


def test_learner_cannot_upload() -> None:
    token = create_user("Learner")

    response = upload(token, "lesson.mp4", b"video-bytes", "video/mp4")

    assert response.status_code == 403


def test_youtube_url_is_validated_and_stored(monkeypatch) -> None:
    with TemporaryDirectory() as temporary_directory:
        source_path = Path(temporary_directory) / "sample.mp4"
        source_path.write_bytes(b"test-video-content")
        source_size = source_path.stat().st_size

        monkeypatch.setattr(
            "app.routes.videos.download_youtube_video",
            lambda url: (source_path, "video/mp4", source_size),
        )
        monkeypatch.setattr("app.routes.videos.convert_to_browser_mp4", lambda path: path)
        token = create_user("Content Creator")
        response = client.post(
            "/videos/youtube",
            headers={"Authorization": f"Bearer {token}"},
            json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

        assert response.status_code == 201
        payload = response.json()
        assert payload["source_type"] == "YOUTUBE"
        assert payload["status"] == "UPLOADED"
        with TestingSessionLocal() as db:
            video = db.scalar(select(Video).where(Video.source_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
            assert video is not None
            assert video.source_type == "YOUTUBE"
            assert video.file_size_bytes == source_size
            assert video.storage_key.endswith(".mp4")
            assert video.storage_key in fake_storage.uploaded
            assert len(fake_storage.uploaded[video.storage_key]) == source_size
            assert video.processing_status == VideoProcessingStatus.UPLOADED


def test_youtube_rejects_invalid_url() -> None:
    token = create_user("Content Creator")
    response = client.post(
        "/videos/youtube",
        headers={"Authorization": f"Bearer {token}"},
        json={"youtube_url": "https://example.com/not-youtube"},
    )

    assert response.status_code == 400
    assert "YouTube" in response.json()["detail"]


def test_youtube_accepts_supported_video_url_forms() -> None:
    urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=ignored",
        "https://youtu.be/dQw4w9WgXcQ?t=10",
        "https://www.youtube.com/shorts/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ]

    assert [validate_youtube_url(url).video_id for url in urls] == ["dQw4w9WgXcQ"] * 4


def test_youtube_download_uses_node_runtime_and_audio_format(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options) -> None:
            captured.update(options)
            self.temp_dir = Path(options["outtmpl"].replace("%(ext)s", "webm")).parent

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

        def download(self, urls) -> None:
            output_path = Path(self.temp_dir) / "clipmind-youtube.webm"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(b"audio-bytes")

    monkeypatch.setattr("app.services.youtube_service.yt_dlp.YoutubeDL", FakeYoutubeDL)
    monkeypatch.setattr("app.services.youtube_service.shutil.which", lambda name: "C:/Program Files/nodejs/node.exe" if name == "node" else None)

    downloaded, mime_type, file_size = __import__("app.services.youtube_service", fromlist=["download_youtube_video"]).download_youtube_video(
        "https://youtu.be/dQw4w9WgXcQ"
    )

    assert captured["format"] == "bestaudio/best"
    assert captured["js_runtimes"] == {"node": {}}
    assert downloaded.exists()
    assert mime_type == "audio/webm"
    assert file_size == len(b"audio-bytes")


def test_youtube_route_keeps_download_available_during_processing_and_cleans_after(monkeypatch) -> None:
    token = create_user("Content Creator")

    with TemporaryDirectory() as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        source_path = temp_dir / "clipmind-youtube.webm"
        source_path.write_bytes(b"audio-data")

        def fake_download(url: str):
            assert source_path.exists()
            return source_path, "audio/webm", source_path.stat().st_size

        def fake_convert(path: Path) -> Path:
            assert path.exists()
            return path

        monkeypatch.setattr("app.routes.videos.download_youtube_video", fake_download)
        monkeypatch.setattr("app.routes.videos.convert_to_browser_mp4", fake_convert)

        response = client.post(
            "/videos/youtube",
            headers={"Authorization": f"Bearer {token}"},
            json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )

        assert response.status_code == 201
        assert not temp_dir.exists()


def test_youtube_access_restriction_is_reported_without_persisting_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routes.videos.download_youtube_video",
        lambda url: (_ for _ in ()).throw(
            YouTubeDownloadError(
                "YouTube requires sign-in or bot verification for this video.",
                code="ACCESS_RESTRICTED",
            )
        ),
    )
    token = create_user("Content Creator")

    response = client.post(
        "/videos/youtube",
        headers={"Authorization": f"Bearer {token}"},
        json={"youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
    )

    assert response.status_code == 422
    assert "requires sign-in" in response.json()["detail"]
    with TestingSessionLocal() as db:
        assert db.scalar(select(Video)) is None


def test_youtube_error_categories_provide_distinct_guidance() -> None:
    cases = [
        ("LOGIN_REQUIRED", "LOGIN_REQUIRED: sign in required"),
        ("BOT_VERIFICATION", "Sign in to confirm you're not a bot"),
        ("VIDEO_UNAVAILABLE", "Private video"),
        ("NETWORK_TIMEOUT", "The operation timed out"),
        ("DOWNLOAD_FAILED", "HTTP Error 502: Bad Gateway"),
    ]

    for expected_code, detail in cases:
        code, message = _classify_download_error(RuntimeError(detail))
        assert code == expected_code
        assert message


@pytest.mark.parametrize(
    ("detail", "expected_code"),
    [
        ("LOGIN_REQUIRED: sign in required", "LOGIN_REQUIRED"),
        ("Sign in to confirm you're not a bot", "BOT_VERIFICATION"),
        ("Private video", "VIDEO_UNAVAILABLE"),
        ("The operation timed out", "NETWORK_TIMEOUT"),
    ],
)
def test_youtube_download_classifies_mocked_ytdlp_failures(monkeypatch, detail: str, expected_code: str) -> None:
    class FailingYoutubeDL:
        def __init__(self, options) -> None:
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback) -> None:
            return None

        def download(self, urls) -> None:
            raise yt_dlp.utils.DownloadError(detail)

    monkeypatch.setattr("app.services.youtube_service.yt_dlp.YoutubeDL", FailingYoutubeDL)

    with pytest.raises(YouTubeDownloadError) as raised:
        from app.services.youtube_service import download_youtube_video

        download_youtube_video("https://youtu.be/dQw4w9WgXcQ")

    assert raised.value.code == expected_code


def test_youtube_requires_content_creator_permission() -> None:
    token = create_user("Learner")
    response = client.post(
        "/videos/youtube",
        headers={"Authorization": f"Bearer {token}"},
        json={"youtube_url": "https://youtu.be/dQw4w9WgXcQ"},
    )

    assert response.status_code == 403


def test_uploaded_video_defaults_to_upload_source_type() -> None:
    token = create_user("Content Creator")
    response = upload(token, "lesson.mp4", b"video-bytes", "video/mp4")

    assert response.status_code == 201
    with TestingSessionLocal() as db:
        video = db.scalar(select(Video).where(Video.filename == "lesson.mp4"))
        assert video is not None
        assert video.source_type == "UPLOAD"
        assert video.source_url is None


def test_cloud_storage_failure_returns_error_without_metadata() -> None:
    fake_storage.fail_upload = True
    token = create_user("Content Creator")

    response = upload(token, "lesson.mp4", b"video-bytes", "video/mp4")

    assert response.status_code == 502
    assert "cloud storage" in response.json()["detail"]
    with TestingSessionLocal() as db:
        assert db.scalar(select(Video)) is None


def test_creator_can_delete_own_video_and_storage_object_is_removed() -> None:
    token = create_user("Content Creator")
    upload_response = upload(token, "delete-me.mp4", b"delete-bytes", "video/mp4")
    video_id = upload_response.json()["id"]

    response = delete_video(token, video_id)

    assert response.status_code == 200
    assert response.json()["message"] == "Video deleted successfully"
    assert response.json()["video_id"] == video_id
    with TestingSessionLocal() as db:
        assert db.scalar(select(Video).where(Video.id == UUID(video_id))) is None
    assert video_id in [item.split("/")[-1].split(".")[0] for item in fake_storage.deleted]


def test_non_owner_cannot_delete_video() -> None:
    owner_token = create_user("Content Creator")
    other_token = create_user("Content Creator")
    upload_response = upload(owner_token, "owned-by-user.mp4", b"video-bytes", "video/mp4")
    video_id = upload_response.json()["id"]

    response = delete_video(other_token, video_id)

    assert response.status_code == 403
    assert "permission" in response.json()["detail"].lower()
