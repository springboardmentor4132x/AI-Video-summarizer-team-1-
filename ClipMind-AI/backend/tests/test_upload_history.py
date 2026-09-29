from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
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
    registration = client.post(
        "/auth/register",
        json={
            "full_name": f"{suffix} {role}",
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


def upload(token: str, filename: str) -> str:
    response = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def get_history(path: str, token: str):
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def test_creator_sees_only_owned_upload_events() -> None:
    creator_token = create_user("Content Creator", "creator")
    other_creator_token = create_user("Content Creator", "other")
    upload(creator_token, "owned.mp4")

    own_history = get_history("/videos/history", creator_token)
    other_history = get_history("/videos/history", other_creator_token)

    assert own_history.status_code == 200
    assert [event["filename"] for event in own_history.json()] == ["owned.mp4"]
    assert other_history.status_code == 200
    assert other_history.json() == []
    event = own_history.json()[0]
    assert event["status"] == "UPLOADED"
    assert event["timestamp"]
    assert "accepted" in event["notes"]


def test_administrator_sees_platform_upload_activity() -> None:
    creator_token = create_user("Content Creator", "creator")
    administrator_token = create_user("Administrator", "admin")
    upload(creator_token, "platform.mp4")

    response = get_history("/admin/upload-history", administrator_token)

    assert response.status_code == 200
    assert [event["filename"] for event in response.json()] == ["platform.mp4"]
    assert response.json()[0]["owner_name"] == "creator Content Creator"


def test_history_reports_current_video_status_and_metadata() -> None:
    creator_token = create_user("Content Creator", "status")
    video_id = upload(creator_token, "status.mp4")

    processing = client.patch(
        f"/videos/{video_id}/status",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"status": "PROCESSING", "notes": "Started"},
    )
    completed = client.patch(
        f"/videos/{video_id}/status",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"status": "COMPLETED", "notes": "Finished"},
    )
    history = get_history("/videos/history", creator_token)

    assert processing.status_code == 200
    assert completed.status_code == 200
    assert history.status_code == 200
    assert len(history.json()) == 1
    assert history.json()[0]["video_id"] == video_id
    assert history.json()[0]["status"] == "COMPLETED"
    assert history.json()[0]["filename"] == "status.mp4"
    assert history.json()[0]["mime_type"] == "video/mp4"
    assert history.json()[0]["file_size_bytes"] == len(b"video-bytes")
    assert history.json()[0]["duration_seconds"] is None
    assert history.json()[0]["source_type"] == "UPLOAD"


def test_history_endpoints_require_their_role_permissions() -> None:
    learner_token = create_user("Learner", "learner")
    creator_token = create_user("Content Creator", "creator")

    assert get_history("/videos/history", learner_token).status_code == 403
    assert get_history("/admin/upload-history", creator_token).status_code == 403
