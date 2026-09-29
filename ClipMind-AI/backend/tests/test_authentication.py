from datetime import datetime, timedelta, timezone
from collections.abc import Generator

from fastapi.testclient import TestClient
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
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


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)


def register_user() -> None:
    response = client.post(
        "/auth/register",
        json={
            "full_name": "Asha Kumar",
            "email": "asha@example.com",
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": "Learner",
        },
    )
    assert response.status_code == 201


def login_user() -> dict[str, object]:
    response = client.post(
        "/auth/login",
        json={"email": "ASHA@example.com", "password": "strong-password"},
    )
    assert response.status_code == 200
    return response.json()


def test_login_returns_jwt_with_safe_claims() -> None:
    register_user()
    payload = login_user()

    assert payload["token_type"] == "bearer"
    assert payload["expires_in"] == settings.access_token_expire_minutes * 60
    assert payload["user_id"]
    assert payload["email"] == "asha@example.com"
    assert payload["role"] == "Learner"
    assert "password" not in payload
    assert "password_hash" not in payload

    claims = jwt.decode(
        payload["access_token"],
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    assert claims["sub"] == payload["user_id"]
    assert claims["email"] == "asha@example.com"
    assert claims["role"] == "Learner"
    assert claims["type"] == "access"
    assert "exp" in claims


def test_current_user_requires_valid_bearer_token() -> None:
    register_user()
    token = login_user()["access_token"]

    missing = client.get("/auth/me")
    valid = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    invalid = client.get("/auth/me", headers={"Authorization": "Bearer invalid-token"})

    assert missing.status_code == 401
    assert valid.status_code == 200
    assert valid.json()["email"] == "asha@example.com"
    assert "password_hash" not in valid.json()
    assert invalid.status_code == 401


def test_login_rejects_wrong_password_and_expired_token() -> None:
    register_user()
    wrong_password = client.post(
        "/auth/login",
        json={"email": "asha@example.com", "password": "wrong-password"},
    )
    expired_token = jwt.encode(
        {
            "sub": "00000000-0000-0000-0000-000000000001",
            "email": "asha@example.com",
            "role": "Learner",
            "type": "access",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    expired = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )

    assert wrong_password.status_code == 401
    assert expired.status_code == 401
