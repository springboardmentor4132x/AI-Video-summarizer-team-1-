from collections.abc import Generator
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import UploadHistory, Video
from app.services.ffmpeg_processing import ProcessingError, convert_to_browser_mp4
from app.services.storage import get_storage


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
client = TestClient(app)


class FakeStorage:
    def upload_fileobj(self, fileobj, storage_key: str, mime_type: str) -> None:
        fileobj.read()

    def download_fileobj(self, storage_key: str, fileobj) -> None:
        fileobj.write(b"video-bytes")

    def delete_object(self, storage_key: str) -> None:
        pass


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: FakeStorage()
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)


def create_creator() -> str:
    assert client.post(
        "/auth/register",
        json={
            "full_name": "FFmpeg Creator",
            "email": "ffmpeg-creator@example.com",
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": "Content Creator",
        },
    ).status_code == 201
    response = client.post(
        "/auth/login",
        json={"email": "ffmpeg-creator@example.com", "password": "strong-password"},
    )
    return response.json()["access_token"]


def upload(token: str) -> str:
    response = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("lesson.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_ffmpeg_processing_extracts_duration_and_completes(monkeypatch) -> None:
    token = create_creator()
    video_id = upload(token)

    def successful_command(command: list[str], **kwargs) -> CompletedProcess[str]:
        if command[0] == "ffprobe":
            return CompletedProcess(command, 0, '{"format":{"duration":"91.4"}}', "")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.ffmpeg_processing.subprocess.run", successful_command)

    response = client.post(f"/videos/{video_id}/process", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["processing_status"] == "COMPLETED"
    with TestingSessionLocal() as db:
        video = db.scalar(select(Video))
        assert video is not None
        assert video.duration_seconds == 91
        assert [event.status.value for event in db.scalars(select(UploadHistory).where(UploadHistory.video_id == video.id)).all()] == [
            "UPLOADED",
            "PROCESSING",
            "COMPLETED",
        ]


def test_convert_to_browser_mp4_creates_playable_output(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    output_paths: list[Path] = []

    def successful_conversion(command: list[str]) -> CompletedProcess[str]:
        output = Path(command[-1])
        output_paths.append(output)
        output.write_bytes(b"h264-aac-mp4")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.ffmpeg_processing._run_command", successful_conversion)

    converted = convert_to_browser_mp4(source)

    assert converted.suffix == ".mp4"
    assert converted.read_bytes() == b"h264-aac-mp4"
    assert output_paths == [converted]
    converted.unlink()


def test_convert_to_browser_mp4_cleans_failed_output(monkeypatch, tmp_path) -> None:
    source = tmp_path / "source.mkv"
    source.write_bytes(b"source")
    output_paths: list[Path] = []

    def failed_conversion(command: list[str]) -> CompletedProcess[str]:
        output_paths.append(Path(command[-1]))
        return CompletedProcess(command, 1, "", "conversion failed")

    monkeypatch.setattr("app.services.ffmpeg_processing._run_command", failed_conversion)

    with pytest.raises(ProcessingError, match="browser-compatible MP4"):
        convert_to_browser_mp4(source)

    assert output_paths and not output_paths[0].exists()


def test_ffmpeg_failure_marks_video_failed(monkeypatch) -> None:
    token = create_creator()
    video_id = upload(token)

    def failed_command(command: list[str], **kwargs) -> CompletedProcess[str]:
        if command[0] == "ffprobe":
            return CompletedProcess(command, 1, "", "invalid data")
        return CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("app.services.ffmpeg_processing.subprocess.run", failed_command)

    response = client.post(f"/videos/{video_id}/process", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Video processing failed"
    with TestingSessionLocal() as db:
        video = db.scalar(select(Video))
        assert video is not None
        assert video.processing_status.value == "FAILED"
        events = db.scalars(select(UploadHistory).where(UploadHistory.video_id == video.id)).all()
        assert events[-1].status.value == "FAILED"
