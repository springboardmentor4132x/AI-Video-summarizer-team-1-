import pytest
from fastapi.testclient import TestClient
from datetime import timedelta, datetime, timezone
from jose import jwt

from app.main import app
from app.core.config import settings
from app.core.security import create_access_token
from app.schemas.user import UserRole

client = TestClient(app)

def test_missing_jwt():
    response = client.get("/auth/test")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"

def test_invalid_jwt():
    response = client.get("/auth/test", headers={"Authorization": "Bearer not_a_real_token"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"

def test_expired_jwt():
    # create_access_token computes expire = now + delta, so a negative delta produces an expired token
    token = create_access_token(subject="1", expires_delta=timedelta(minutes=-10))
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"

def test_valid_authenticated_user_but_forbidden_role():
    # User is valid but doesn't have the ADMINISTRATOR role
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {"exp": expire, "sub": "1", "role": UserRole.LEARNER}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Operation not permitted"

def test_valid_authenticated_user_allowed_role():
    # User has the ADMINISTRATOR role
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {"exp": expire, "sub": "1", "role": UserRole.ADMINISTRATOR}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["message"] == "You have administrator access!"
    assert response.json()["user_id"] == 1
    assert response.json()["role"] == "Administrator"

def test_invalid_role_in_token():
    # Token has a role that is not part of our UserRole enum
    expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode = {"exp": expire, "sub": "1", "role": "SuperHacker"}
    token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    
    response = client.get("/auth/test", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"
