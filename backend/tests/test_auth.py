# pyrefly: ignore [missing-import]
import pytest
from fastapi.testclient import TestClient
from datetime import timedelta, datetime, timezone
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.schemas.user import UserRole
from fastapi import Depends
from app.dependencies.auth import require_role
from app.db.session import get_db, Base
from app.models.user import User

# Test Database Setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_auth.sqlite"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

def create_test_user(db_session, email="test@example.com", password="password123", role="learner"):
    user = User(
        name="Test User",
        email=email,
        password=get_password_hash(password),
        role=role
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user

# --- Registration Tests ---

def test_register_success():
    response = client.post(
        "/auth/register",
        json={"name": "New User", "email": "new@example.com", "password": "securepassword", "role": "Content Creator"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["role"] == "Content Creator"
    assert "password" not in data
    
    # Check DB directly to ensure password is a hash and role is lowercase
    db = TestingSessionLocal()
    user = db.query(User).filter(User.email == "new@example.com").first()
    assert user is not None
    assert user.role == "content creator"
    assert user.password != "securepassword"
    assert verify_password("securepassword", user.password)
    db.close()

def test_register_duplicate_email():
    client.post(
        "/auth/register",
        json={"name": "User 1", "email": "duplicate@example.com", "password": "password123", "role": "Learner"}
    )
    response = client.post(
        "/auth/register",
        json={"name": "User 2", "email": "duplicate@example.com", "password": "password123", "role": "Learner"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"

def test_register_invalid_role():
    response = client.post(
        "/auth/register",
        json={"name": "User", "email": "badrole@example.com", "password": "password123", "role": "Super Admin"}
    )
    assert response.status_code == 422 # Pydantic validation error

# --- Login Tests ---

def test_login_success():
    db = TestingSessionLocal()
    create_test_user(db, email="login@example.com", password="password123")
    db.close()
    
    response = client.post(
        "/auth/login",
        json={"email": "login@example.com", "password": "password123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_wrong_password():
    db = TestingSessionLocal()
    create_test_user(db, email="login2@example.com", password="password123")
    db.close()
    
    response = client.post(
        "/auth/login",
        json={"email": "login2@example.com", "password": "wrongpassword"}
    )
    assert response.status_code == 401

def test_login_nonexistent_email():
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "password123"}
    )
    assert response.status_code == 401

# --- Auth / get_current_user Tests ---

def test_auth_missing_jwt():
    response = client.get("/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_auth_invalid_jwt():
    response = client.get("/auth/me", headers={"Authorization": "Bearer not_a_real_token"})
    assert response.status_code == 401

def test_auth_expired_jwt():
    db = TestingSessionLocal()
    user = create_test_user(db)
    token = create_access_token(subject=str(user.id), expires_delta=timedelta(minutes=-10))
    db.close()
    
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

def test_auth_deleted_user():
    token = create_access_token(subject="9999") # User ID doesn't exist
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

# --- GET /auth/me Tests ---

def test_get_me_success():
    db = TestingSessionLocal()
    user = create_test_user(db, email="me@example.com")
    token = create_access_token(subject=str(user.id))
    db.close()
    
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "me@example.com"
    assert "password" not in data
    assert data["role"] == "Learner" # Should be title-cased by schema

# --- RBAC Tests ---

@app.get("/auth/test-multi-role", dependencies=[Depends(require_role([UserRole.ADMINISTRATOR, UserRole.EDUCATOR]))])
def mock_multi_role_endpoint():
    return {"message": "success"}

def test_rbac_allowed_role():
    db = TestingSessionLocal()
    user = create_test_user(db, role="administrator")
    token = create_access_token(subject=str(user.id))
    db.close()
    
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_rbac_forbidden_role():
    db = TestingSessionLocal()
    user = create_test_user(db, role="learner")
    token = create_access_token(subject=str(user.id))
    db.close()
    
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

def test_rbac_multi_role_accepted():
    db = TestingSessionLocal()
    user = create_test_user(db, role="educator")
    token = create_access_token(subject=str(user.id))
    db.close()
    
    response = client.get("/auth/test-multi-role", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_rbac_stale_role_in_jwt_follows_db():
    db = TestingSessionLocal()
    # Database says administrator
    user = create_test_user(db, role="administrator")
    # But JWT says learner (simulating a token issued before a role upgrade)
    token = create_access_token(subject=str(user.id), extra_data={"role": "Learner"})
    db.close()
    
    # Should follow database (administrator), so access to /auth/test (admin only) is allowed
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200

def test_password_hashing():
    plain = "testpass"
    h1 = get_password_hash(plain)
    h2 = get_password_hash(plain)
    assert h1 != plain
    assert h1 != h2

def test_password_verification():
    plain = "testpass"
    h = get_password_hash(plain)
    assert verify_password(plain, h)
    assert not verify_password("wrong", h)
