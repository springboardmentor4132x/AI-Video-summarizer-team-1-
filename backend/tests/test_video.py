import os
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("DATABASE_URL", "sqlite://")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.user import User
from app.models.video import Video
from app.routers import video as video_router
from app.services import ffmpeg_service


TEST_DATABASE_URL = "sqlite:///./test_video.sqlite"
engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def configure_test_app(monkeypatch, tmp_path):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(video_router, "UPLOAD_DIR", tmp_path / "uploads")
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def create_user(email: str) -> User:
    db = TestingSessionLocal()
    user = User(name="Video User", email=email, password="hash", role="learner")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def use_current_user(user: User):
    app.dependency_overrides[video_router.get_current_user] = lambda: user


def test_ffmpeg_success_uses_safe_h264_aac_command(monkeypatch, tmp_path):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    input_path.write_bytes(b"input")
    commands = []

    def fake_run(command, **kwargs):
        commands.append((command, kwargs))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ffmpeg_service.subprocess, "run", fake_run)

    assert ffmpeg_service.process_video(str(input_path), str(output_path)) is True
    assert commands[0][0] == [
        "ffmpeg", "-nostdin", "-i", str(input_path), "-c:v", "libx264",
        "-c:a", "aac", "-y", str(output_path),
    ]


def test_ffmpeg_missing_input_returns_false_and_removes_output(tmp_path):
    output_path = tmp_path / "partial.mp4"
    output_path.write_bytes(b"partial")

    assert ffmpeg_service.process_video(str(tmp_path / "missing.mp4"), str(output_path)) is False
    assert not output_path.exists()


def test_ffmpeg_failure_removes_partial_output(monkeypatch, tmp_path):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "partial.mp4"
    input_path.write_bytes(b"input")
    output_path.write_bytes(b"partial")
    monkeypatch.setattr(
        ffmpeg_service.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    assert ffmpeg_service.process_video(str(input_path), str(output_path)) is False
    assert not output_path.exists()


def test_upload_requires_bearer_token():
    response = client.post("/videos/upload", files={"file": ("video.mp4", b"data", "video/mp4")})

    assert response.status_code == 401


def test_authenticated_upload_streams_and_creates_owned_record(monkeypatch):
    user = create_user("owner@example.com")
    use_current_user(user)
    monkeypatch.setattr(video_router, "process_video_background", lambda *_args: None)

    response = client.post(
        "/videos/upload",
        files={"file": ("../../original.MP4", b"video-data", "video/mp4")},
    )

    assert response.status_code == 201
    video_id = response.json()["id"]
    db = TestingSessionLocal()
    video = db.get(Video, video_id)
    db.close()
    assert video.user_id == user.id
    assert video.filename == "original.MP4"
    assert video.status == "uploaded"
    stored_path = video_router.UPLOAD_DIR / Path(video.file_path).name
    assert stored_path.exists()
    assert stored_path.suffix == ".mp4"
    assert stored_path.stem != "original"


def test_upload_size_limit_removes_partial_file(monkeypatch):
    user = create_user("limit@example.com")
    use_current_user(user)
    monkeypatch.setattr(video_router, "MAX_FILE_SIZE", 3)

    response = client.post(
        "/videos/upload",
        files={"file": ("large.mp4", b"four", "video/mp4")},
    )

    assert response.status_code == 413
    assert not video_router.UPLOAD_DIR.exists() or not list(video_router.UPLOAD_DIR.glob("*"))


def test_status_endpoint_returns_owned_video_status():
    user = create_user("status-owner@example.com")
    use_current_user(user)
    db = TestingSessionLocal()
    video = Video(user_id=user.id, filename="video.mp4", file_path="/tmp/video.mp4", status="processing")
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    response = client.get(f"/videos/{video_id}/status")

    assert response.status_code == 200
    assert response.json() == {"id": video_id, "status": "processing"}


def test_status_endpoint_hides_videos_owned_by_another_user():
    owner = create_user("actual-owner@example.com")
    requester = create_user("other-user@example.com")
    use_current_user(requester)
    db = TestingSessionLocal()
    video = Video(user_id=owner.id, filename="video.mp4", file_path="/tmp/video.mp4", status="completed")
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()

    response = client.get(f"/videos/{video_id}/status")

    assert response.status_code == 404
    assert response.json()["detail"] == "Video not found"


@pytest.mark.parametrize("ffmpeg_result, expected_status", [(True, "completed"), (False, "failed")])
def test_background_processing_updates_video_status(monkeypatch, tmp_path, ffmpeg_result, expected_status):
    user = create_user(f"processing-{ffmpeg_result}@example.com")
    db = TestingSessionLocal()
    video = Video(user_id=user.id, filename="video.mp4", file_path="input.mp4", status="uploaded")
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()
    monkeypatch.setattr(video_router, "SessionLocal", TestingSessionLocal)
    observed_statuses = []

    def fake_process_video(**_kwargs):
        processing_db = TestingSessionLocal()
        processing_video = processing_db.get(Video, video_id)
        observed_statuses.append(processing_video.status)
        processing_db.close()
        return ffmpeg_result

    monkeypatch.setattr(video_router, "process_video", fake_process_video)

    video_router.process_video_background(video_id, str(tmp_path / "input.mp4"), str(tmp_path / "output.mp4"))

    db = TestingSessionLocal()
    processed = db.get(Video, video_id)
    db.close()
    assert observed_statuses == ["processing"]
    assert processed.status == expected_status

@pytest.mark.skip(reason="Pending MongoDB integration")
def test_background_processing_creates_and_updates_one_transcript(monkeypatch, tmp_path):
    user = create_user("transcript-owner@example.com")
    db = TestingSessionLocal()
    video = Video(user_id=user.id, filename="video.mp4", file_path="input.mp4", status="uploaded")
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()
    monkeypatch.setattr(video_router, "SessionLocal", TestingSessionLocal)
    transcript_texts = iter(["First transcript", "Updated transcript"])

    monkeypatch.setattr(video_router, "process_video", lambda **_kwargs: True)

    def fake_extract_audio(video_path, audio_path):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"audio")
        return SimpleNamespace(status="completed", audio_path=audio_path)

    def fake_transcribe_audio(_audio_path):
        return SimpleNamespace(
            status="completed",
            text=next(transcript_texts),
            segments=[{"text": "segment"}],
            language="en",
        )

    monkeypatch.setattr(video_router, "extract_audio", fake_extract_audio)
    monkeypatch.setattr(video_router, "transcribe_audio", fake_transcribe_audio)

    video_router.process_video_background(
        video_id,
        str(tmp_path / "input.mp4"),
        str(tmp_path / "output.mp4"),
    )
    video_router.process_video_background(
        video_id,
        str(tmp_path / "input.mp4"),
        str(tmp_path / "output.mp4"),
    )

    db = TestingSessionLocal()
    transcripts = db.query(Transcript).filter(Transcript.video_id == video_id).all()
    db.close()
    assert len(transcripts) == 1
    assert transcripts[0].full_text == "Updated transcript"
    assert transcripts[0].segments == [{"text": "segment"}]
    assert not list(video_router.UPLOAD_DIR.glob("*_transcription.wav"))

@pytest.mark.skip(reason="Pending MongoDB integration")
def test_background_processing_handles_audio_extraction_failure(monkeypatch, tmp_path):
    user = create_user("audio-failure@example.com")
    db = TestingSessionLocal()
    video = Video(user_id=user.id, filename="video.mp4", file_path="input.mp4", status="uploaded")
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()
    monkeypatch.setattr(video_router, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(video_router, "process_video", lambda **_kwargs: True)

    def failed_extract(video_path, audio_path):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"partial")
        return SimpleNamespace(
            status="failed",
            audio_path=None,
            error_code="ffmpeg_failed",
        )

    monkeypatch.setattr(video_router, "extract_audio", failed_extract)
    monkeypatch.setattr(
        video_router,
        "transcribe_audio",
        lambda _audio_path: (_ for _ in ()).throw(AssertionError("transcription should not run")),
    )

    video_router.process_video_background(
        video_id,
        str(tmp_path / "input.mp4"),
        str(tmp_path / "output.mp4"),
    )

    db = TestingSessionLocal()
    processed = db.get(Video, video_id)
    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    db.close()
    assert processed.status == "completed"
    assert transcript is None
    assert not list(video_router.UPLOAD_DIR.glob("*_transcription.wav"))

@pytest.mark.skip(reason="Pending MongoDB integration")
def test_background_processing_handles_transcription_failure(monkeypatch, tmp_path):
    user = create_user("transcription-failure@example.com")
    db = TestingSessionLocal()
    video = Video(user_id=user.id, filename="video.mp4", file_path="input.mp4", status="uploaded")
    db.add(video)
    db.commit()
    db.refresh(video)
    video_id = video.id
    db.close()
    monkeypatch.setattr(video_router, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(video_router, "process_video", lambda **_kwargs: True)

    def successful_extract(video_path, audio_path):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"audio")
        return SimpleNamespace(status="completed", audio_path=audio_path)

    monkeypatch.setattr(video_router, "extract_audio", successful_extract)
    monkeypatch.setattr(
        video_router,
        "transcribe_audio",
        lambda _audio_path: SimpleNamespace(status="failed", error_code="transcription_failed"),
    )

    video_router.process_video_background(
        video_id,
        str(tmp_path / "input.mp4"),
        str(tmp_path / "output.mp4"),
    )

    db = TestingSessionLocal()
    processed = db.get(Video, video_id)
    transcript = db.query(Transcript).filter(Transcript.video_id == video_id).first()
    db.close()
    assert processed.status == "completed"
    assert transcript is None
    assert not list(video_router.UPLOAD_DIR.glob("*_transcription.wav"))
