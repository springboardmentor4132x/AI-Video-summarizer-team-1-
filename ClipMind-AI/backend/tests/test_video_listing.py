from collections.abc import Generator
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Video, VideoProcessingStatus
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
    response = client.post("/auth/login", json={"email": email, "password": "strong-password"})
    return response.json()["access_token"]


def upload(token: str, filename: str) -> str:
    response = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": (filename, b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_video_listing_is_role_scoped() -> None:
    creator = create_user("Content Creator", "creator")
    other_creator = create_user("Content Creator", "other")
    learner = create_user("Learner", "learner")
    administrator = create_user("Administrator", "admin")
    own_id = upload(creator, "own.mp4")
    upload(other_creator, "other.mp4")

    with TestingSessionLocal() as db:
        db.get(Video, UUID(own_id)).processing_status = VideoProcessingStatus.COMPLETED
        db.commit()

    creator_list = client.get("/videos/", headers={"Authorization": f"Bearer {creator}"})
    other_list = client.get("/videos/", headers={"Authorization": f"Bearer {other_creator}"})
    learner_list = client.get("/videos/", headers={"Authorization": f"Bearer {learner}"})
    admin_list = client.get("/videos/", headers={"Authorization": f"Bearer {administrator}"})

    assert [item["filename"] for item in creator_list.json()] == ["own.mp4"]
    assert [item["filename"] for item in other_list.json()] == ["other.mp4"]
    assert [item["filename"] for item in learner_list.json()] == ["own.mp4"]
    assert {item["filename"] for item in admin_list.json()} == {"own.mp4", "other.mp4"}
    assert all("storage_key" not in item for item in admin_list.json())


def test_video_listing_requires_authentication() -> None:
    response = client.get("/videos/")
    assert response.status_code == 401
