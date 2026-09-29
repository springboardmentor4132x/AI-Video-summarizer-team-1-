from collections.abc import Generator
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models import Video
from app.services.storage import get_storage


created_paths: list[Path] = []
backend_uploads = Path(__file__).resolve().parents[1] / "uploads"


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
client = TestClient(app)


class LocalTestStorage:
    def __init__(self, path: Path) -> None:
        from app.config import Settings
        from app.services.storage import LocalStorage

        self.storage = LocalStorage(
            Settings(
                db_user="user",
                db_password="password",
                db_host="localhost",
                db_port=5432,
                db_name="database",
                jwt_secret_key="secret",
                storage_backend="local",
                local_storage_path=str(path),
            )
        )

    def upload_fileobj(self, fileobj, storage_key: str, mime_type: str) -> None:
        self.storage.upload_fileobj(fileobj, storage_key, mime_type)

    def delete_object(self, storage_key: str) -> None:
        self.storage.delete_object(storage_key)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    created_paths.clear()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: LocalTestStorage(Path("uploads"))
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)
    for path in created_paths:
        path.unlink(missing_ok=True)


def test_authenticated_upload_persists_local_file_and_media_route() -> None:
    email = "local-flow@example.com"
    registration = client.post(
        "/auth/register",
        json={
            "full_name": "Local Flow",
            "email": email,
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": "Content Creator",
        },
    )
    assert registration.status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": "strong-password"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    upload = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("demo.webm", b"local-video-bytes", "video/webm")},
    )

    assert upload.status_code == 201
    video_id = upload.json()["id"]
    with TestingSessionLocal() as db:
        video = db.scalar(select(Video).where(Video.id == UUID(video_id)))
        assert video is not None
        local_path = backend_uploads / video.storage_key
    created_paths.append(local_path)
    assert local_path.is_file()
    assert local_path.read_bytes() == b"local-video-bytes"
    assert client.get(f"/media/{video.storage_key}").status_code == 200