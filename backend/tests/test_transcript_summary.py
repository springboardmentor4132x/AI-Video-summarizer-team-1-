from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, get_password_hash
from app.db.session import Base, get_db
from app.main import app
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video
from app.routers.videos import process_video_background

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_transcript_summary.sqlite"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    previous_override = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield
    finally:
        Base.metadata.drop_all(bind=engine)
        if previous_override is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_override


def create_user(db_session, email: str = "creator@example.com", role: str = "content creator") -> User:
    user = User(
        name="Creator User",
        email=email,
        password=get_password_hash("password123"),
        role=role,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_video(db_session, user_id: int, filename: str = "demo.mp4") -> Video:
    video = Video(
        user_id=user_id,
        filename=filename,
        file_path="/tmp/demo.mp4",
        status="uploaded",
    )
    db_session.add(video)
    db_session.commit()
    db_session.refresh(video)
    return video


def test_post_transcript_generates_timestamped_transcript(monkeypatch, tmp_path):
    db = TestingSessionLocal()
    user = create_user(db, email="transcript@example.com")
    video = create_video(db, user_id=user.id, filename="lesson.mp4")
    token = create_access_token(subject=str(user.id))
    db.close()

    video_path = tmp_path / "lesson.mp4"
    audio_path = tmp_path / "lesson.wav"
    video_path.write_bytes(b"fake video")

    monkeypatch.setattr(
        "app.routers.videos.extract_audio",
        lambda video_path, audio_path: SimpleNamespace(status="completed", audio_path=str(audio_path)),
    )
    monkeypatch.setattr(
        "app.routers.videos.transcribe_audio",
        lambda audio_file, language_hint=None: SimpleNamespace(
            status="completed",
            text="Welcome to the lesson. We will discuss AI tools.",
            language="en",
            segments=[
                {"start": 0.0, "end": 3.2, "text": "Welcome to the lesson."},
                {"start": 3.2, "end": 8.4, "text": "We will discuss AI tools."},
            ],
            error_code=None,
            error_message=None,
        ),
    )

    response = client.post(
        f"/videos/{video.id}/transcript",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == video.id
    assert data["status"] == "COMPLETED"
    assert data["segments"][0]["text"] == "Welcome to the lesson."
    assert "AI tools" in data["text"]


def test_summary_uses_completed_transcript_instead_of_raw_video():
    db = TestingSessionLocal()
    user = create_user(db, email="summary@example.com")
    video = create_video(db, user_id=user.id, filename="lecture.mp4")
    video_id = video.id
    transcript = Transcript(
        video_id=video_id,
        text="The session explains the AI workflow. It covers model evaluation, governance, and deployment in clear steps.",
        language="en",
        status=TranscriptStatus.COMPLETED,
        segments=[
            {"start": 0.0, "end": 4.0, "text": "The session explains the AI workflow."},
            {"start": 4.0, "end": 8.0, "text": "It covers model evaluation, governance, and deployment in clear steps."},
        ],
    )
    db.add(transcript)
    db.commit()
    token = create_access_token(subject=str(user.id))
    db.close()

    response = client.post(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "AI workflow" in data["content"]
    assert "governance" in data["content"]
    assert "deployment" in data["content"]


def test_get_summary_requires_completed_transcript():
    db = TestingSessionLocal()
    user = create_user(db, email="pending-summary@example.com")
    video = create_video(db, user_id=user.id, filename="pending.mp4")
    video_id = video.id
    db.add(
        Transcript(
            video_id=video.id,
            text="Transcript still processing.",
            status=TranscriptStatus.PROCESSING,
        )
    )
    db.commit()
    token = create_access_token(subject=str(user.id))
    db.close()

    response = client.get(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Transcript must be completed before summary generation"


def test_background_audio_failure_marks_video_failed(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(db, email="audio-failure@example.com")
    video = create_video(db, user_id=user.id)
    video_id = video.id
    db.close()

    monkeypatch.setattr("app.routers.videos.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.routers.videos.process_video", lambda input_path, output_path: True)
    monkeypatch.setattr(
        "app.routers.videos.extract_audio",
        lambda video_path, audio_path: SimpleNamespace(status="failed", audio_path=None),
    )

    client_video_path = "audio-failure-input.mp4"
    process_video_background(video_id, client_video_path, "audio-failure-output.mp4")

    db = TestingSessionLocal()
    assert db.query(Video).filter(Video.id == video_id).one().status == "failed"
    db.close()


def test_background_whisper_failure_marks_video_failed(monkeypatch):
    db = TestingSessionLocal()
    user = create_user(db, email="whisper-failure@example.com")
    video = create_video(db, user_id=user.id)
    video_id = video.id
    db.close()

    monkeypatch.setattr("app.routers.videos.SessionLocal", TestingSessionLocal)
    monkeypatch.setattr("app.routers.videos.process_video", lambda input_path, output_path: True)
    monkeypatch.setattr(
        "app.routers.videos.extract_audio",
        lambda video_path, audio_path: SimpleNamespace(status="completed", audio_path="audio.wav"),
    )
    monkeypatch.setattr(
        "app.routers.videos.transcribe_audio",
        lambda audio_path: SimpleNamespace(status="failed"),
    )

    process_video_background(video_id, "whisper-failure-input.mp4", "whisper-failure-output.mp4")

    db = TestingSessionLocal()
    assert db.query(Video).filter(Video.id == video_id).one().status == "failed"
    db.close()
