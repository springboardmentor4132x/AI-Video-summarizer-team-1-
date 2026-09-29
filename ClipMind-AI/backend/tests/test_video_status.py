from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Transcript, TranscriptStatus, UploadHistory, Video, VideoProcessingStatus
from app.services.video_processing import reconcile_terminal_transcript_statuses
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


def create_user(role: str, suffix: str) -> str:
    email = f"{role.lower().replace(' ', '-')}-{suffix}@example.com"
    assert client.post(
        "/auth/register",
        json={
            "full_name": f"{suffix} {role}",
            "email": email,
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": role,
        },
    ).status_code == 201
    response = client.post(
        "/auth/login",
        json={"email": email, "password": "strong-password"},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def upload(token: str) -> str:
    response = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("lesson.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def status_request(video_id: str, token: str, status: str, notes: str | None = None):
    return client.patch(
        f"/videos/{video_id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": status, "notes": notes},
    )


def test_status_lifecycle_updates_video_and_history() -> None:
    token = create_user("Content Creator", "creator")
    video_id = upload(token)

    initial = client.get("/videos/status", headers={"Authorization": f"Bearer {token}"})
    processing = status_request(video_id, token, "processing", "Processing started")
    completed = status_request(video_id, token, "completed", "Processing completed")

    assert initial.status_code == 200
    assert initial.json()[0]["processing_status"] == "UPLOADED"
    assert processing.status_code == 200
    assert processing.json()["processing_status"] == "PROCESSING"
    assert processing.json()["latest_note"] == "Processing started"
    assert completed.status_code == 200
    assert completed.json()["processing_status"] == "COMPLETED"

    with TestingSessionLocal() as db:
        video = db.scalar(select(Video).where(Video.id == UUID(video_id)))
        assert video is not None
        assert video.processing_status.value == "COMPLETED"
        events = db.scalars(select(UploadHistory).where(UploadHistory.video_id == video.id)).all()
        assert [event.status.value for event in events] == ["UPLOADED", "PROCESSING", "COMPLETED"]


def test_invalid_transition_returns_conflict() -> None:
    token = create_user("Educator", "educator")
    video_id = upload(token)

    response = status_request(video_id, token, "completed")

    assert response.status_code == 409
    assert "UPLOADED" in response.json()["detail"]


def test_status_access_is_scoped_to_owner_or_administrator() -> None:
    owner_token = create_user("Content Creator", "owner")
    other_token = create_user("Content Creator", "other")
    learner_token = create_user("Learner", "learner")
    admin_token = create_user("Administrator", "admin")
    video_id = upload(owner_token)

    assert client.get("/videos/status", headers={"Authorization": f"Bearer {learner_token}"}).status_code == 403
    assert status_request(video_id, other_token, "processing").status_code == 403
    assert status_request(video_id, admin_token, "processing").status_code == 200
    assert len(client.get("/videos/status", headers={"Authorization": f"Bearer {admin_token}"}).json()) == 1


def test_reconciliation_only_updates_processing_videos_with_terminal_transcripts() -> None:
    token = create_user("Content Creator", "reconcile")
    video_id = upload(token)
    with TestingSessionLocal() as db:
        video = db.scalar(select(Video).where(Video.id == UUID(video_id)))
        assert video is not None
        video.processing_status = VideoProcessingStatus.PROCESSING
        db.add(Transcript(video_id=video.id, status=TranscriptStatus.COMPLETED, text="Transcript"))
        db.commit()

        assert reconcile_terminal_transcript_statuses(db, user_id=video.user_id) == 1
        db.refresh(video)
        assert video.processing_status == VideoProcessingStatus.COMPLETED
        assert reconcile_terminal_transcript_statuses(db, user_id=video.user_id) == 0
