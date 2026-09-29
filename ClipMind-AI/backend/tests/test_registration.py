from collections.abc import Generator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.passwords import verify_password
from app.database import Base, get_db
from app.main import app
from app.models import User


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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)


def test_registers_user_with_legacy_role_and_hashed_password() -> None:
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Asha Kumar",
            "email": "ASHA@example.com",
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": "Learner",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "asha@example.com"
    assert payload["role"] == "Learner"
    assert "password" not in payload
    assert "password_hash" not in payload

    with TestingSessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "asha@example.com"))
        assert user is not None
        assert user.role == "Learner"
        assert user.password_hash != "strong-password"
        assert verify_password("strong-password", user.password_hash)


def test_rejects_duplicate_email() -> None:
    payload = {
        "full_name": "Asha Kumar",
        "email": "asha@example.com",
        "password": "strong-password",
        "confirm_password": "strong-password",
        "role": "Learner",
    }
    assert client.post("/auth/register", json=payload).status_code == 201

    duplicate = client.post("/auth/register", json=payload)

    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "An account with this email already exists"


def test_rejects_password_mismatch_and_invalid_email() -> None:
    mismatch = client.post(
        "/auth/register",
        json={
            "full_name": "Asha Kumar",
            "email": "asha@example.com",
            "password": "strong-password",
            "confirm_password": "different-password",
            "role": "Learner",
        },
    )
    invalid_email = client.post(
        "/auth/register",
        json={
            "full_name": "Asha Kumar",
            "email": "not-an-email",
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": "Learner",
        },
    )

    assert mismatch.status_code == 422
    assert invalid_email.status_code == 422
