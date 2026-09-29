from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)


def create_user(role: str) -> str:
    registration = client.post(
        "/auth/register",
        json={
            "full_name": f"Test {role}",
            "email": f"{role.lower().replace(' ', '-')}@example.com",
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": role,
        },
    )
    assert registration.status_code == 201

    login = client.post(
        "/auth/login",
        json={
            "email": f"{role.lower().replace(' ', '-')}@example.com",
            "password": "strong-password",
        },
    )
    assert login.status_code == 200
    return login.json()["access_token"]


def request(path: str, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.get(path, headers=headers)


def test_unauthenticated_user_is_rejected() -> None:
    response = request("/rbac/admin/users")

    assert response.status_code == 401


def test_content_creator_access() -> None:
    token = create_user("Content Creator")

    assert request("/rbac/creator/uploads", token).status_code == 200
    assert request("/rbac/creator/history", token).status_code == 200
    assert request("/rbac/learner/content", token).status_code == 403
    assert request("/rbac/educator/content", token).status_code == 403
    assert request("/rbac/admin/users", token).status_code == 403


def test_learner_access() -> None:
    token = create_user("Learner")

    assert request("/rbac/learner/content", token).status_code == 200
    assert request("/rbac/creator/uploads", token).status_code == 403
    assert request("/rbac/educator/content", token).status_code == 403
    assert request("/rbac/admin/platform", token).status_code == 403


def test_educator_access() -> None:
    token = create_user("Educator")

    assert request("/rbac/educator/content", token).status_code == 200
    assert request("/rbac/creator/uploads", token).status_code == 403
    assert request("/rbac/learner/content", token).status_code == 403
    assert request("/rbac/admin/users", token).status_code == 403


def test_administrator_access() -> None:
    token = create_user("Administrator")

    assert request("/rbac/creator/uploads", token).status_code == 200
    assert request("/rbac/learner/content", token).status_code == 200
    assert request("/rbac/educator/content", token).status_code == 200
    assert request("/rbac/admin/users", token).status_code == 200
    assert request("/rbac/admin/platform", token).status_code == 200
