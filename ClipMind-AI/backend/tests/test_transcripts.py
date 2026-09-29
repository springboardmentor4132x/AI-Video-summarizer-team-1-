from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Transcript, TranscriptStatus, Video, VideoProcessingStatus
from app.services.storage import get_storage
from app.services.speech_to_text import SpeechToTextError


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
client = TestClient(app)


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def upload_fileobj(self, fileobj, storage_key: str, mime_type: str) -> None:
        self.files[storage_key] = fileobj.read()

    def download_fileobj(self, storage_key: str, fileobj) -> None:
        fileobj.write(self.files[storage_key])

    def delete_object(self, storage_key: str) -> None:
        self.files.pop(storage_key, None)


fake_storage = FakeStorage()


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    fake_storage.files.clear()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: fake_storage
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)


def create_user(role: str, suffix: str) -> str:
    email = f"{suffix}@example.com"
    registration = client.post(
        "/auth/register",
        json={
            "full_name": f"Test {suffix}",
            "email": email,
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": role,
        },
    )
    assert registration.status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": "strong-password"})
    assert login.status_code == 200
    return login.json()["access_token"]


def create_video(token: str) -> str:
    response = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("lesson.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_creator_can_generate_edit_download_and_read_transcript(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "creator")
    video_id = create_video(creator_token)
    monkeypatch.setattr(
        "app.services.transcript.transcribe",
        lambda path: {
            "text": "Welcome to the lesson.",
            "segments": [{"start_time": 0.0, "end_time": 2.0, "text": "Welcome to the lesson."}],
            "language": "en",
        },
    )

    generated = client.post(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {creator_token}"})
    assert generated.status_code == 200
    assert generated.json()["status"] == "COMPLETED"
    assert generated.json()["segments"][0]["start_time"] == 0

    updated = client.patch(
        f"/videos/{video_id}/transcript",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"text": "Welcome to the edited lesson."},
    )
    assert updated.status_code == 200
    assert updated.json()["text"] == "Welcome to the edited lesson."

    fetched = client.get(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {creator_token}"})
    downloaded = client.get(
        f"/videos/{video_id}/transcript/download", headers={"Authorization": f"Bearer {creator_token}"}
    )
    assert fetched.status_code == 200
    assert downloaded.status_code == 200
    assert downloaded.text == "Welcome to the edited lesson."
    with TestingSessionLocal() as db:
        transcript = db.scalar(select(Transcript).where(Transcript.video_id == UUID(video_id)))
        assert transcript is not None
        assert transcript.status == TranscriptStatus.COMPLETED


def test_transcription_file_is_closed_before_provider_and_cleaned_after(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "windows")
    video_id = create_video(creator_token)
    observed_path = None

    def fake_transcribe(path):
        nonlocal observed_path
        observed_path = path
        assert path.is_file()
        assert path.read_bytes() == b"video-bytes"
        return {"text": "Transcript", "segments": [], "language": "en"}

    monkeypatch.setattr("app.services.transcript.transcribe", fake_transcribe)
    response = client.post(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 200
    assert observed_path is not None
    assert not observed_path.exists()


def test_transcription_file_is_cleaned_when_provider_fails(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "failure")
    video_id = create_video(creator_token)
    observed_path = None

    def failing_transcribe(path):
        nonlocal observed_path
        observed_path = path
        raise SpeechToTextError("provider failed")

    monkeypatch.setattr("app.services.transcript.transcribe", failing_transcribe)
    response = client.post(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 422
    assert "provider failed" in response.json()["detail"]
    assert observed_path is not None
    assert not observed_path.exists()


def test_learner_cannot_generate_or_edit_transcript() -> None:
    creator_token = create_user("Content Creator", "owner")
    learner_token = create_user("Learner", "learner")
    video_id = create_video(creator_token)

    generate = client.post(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {learner_token}"})
    edit = client.patch(
        f"/videos/{video_id}/transcript",
        headers={"Authorization": f"Bearer {learner_token}"},
        json={"text": "unauthorized"},
    )
    assert generate.status_code == 403
    assert edit.status_code == 403


def test_duplicate_transcript_generation_is_rejected() -> None:
    creator_token = create_user("Content Creator", "duplicate")
    video_id = create_video(creator_token)
    with TestingSessionLocal() as db:
        video = db.scalar(select(Video).where(Video.id == UUID(video_id)))
        assert video is not None
        video.transcript = Transcript(video_id=video.id, status=TranscriptStatus.PROCESSING)
        db.commit()

    response = client.post(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 409
    assert "already in progress" in response.json()["detail"]


def test_invalid_transcript_segment_range_is_rejected() -> None:
    creator_token = create_user("Content Creator", "timestamps")
    video_id = create_video(creator_token)
    with TestingSessionLocal() as db:
        db.add(Transcript(
            video_id=UUID(video_id),
            text="Existing transcript",
            status=TranscriptStatus.COMPLETED,
            segments=[{"start_time": 0, "end_time": 1, "text": "Existing"}],
        ))
        db.commit()
    response = client.patch(
        f"/videos/{video_id}/transcript",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"text": "Transcript", "segments": [{"start_time": 4, "end_time": 2, "text": "Invalid"}]},
    )

    assert response.status_code == 422


def test_transcript_requires_authentication_and_hides_other_users_video() -> None:
    owner_token = create_user("Content Creator", "owner")
    other_token = create_user("Content Creator", "other")
    video_id = create_video(owner_token)

    unauthenticated = client.get(f"/videos/{video_id}/transcript")
    other_user = client.get(f"/videos/{video_id}/transcript", headers={"Authorization": f"Bearer {other_token}"})
    assert unauthenticated.status_code == 401
    assert other_user.status_code == 403