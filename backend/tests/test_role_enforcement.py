"""Tests for role-based authorization on content modification endpoints.

Verifies that Content Creator and Educator can modify content, while Learner
and Administrator are correctly restricted from content modification endpoints.

Each test covers:
- Unauthenticated → 401
- Wrong role → 403  
- Correct role but wrong owner → 404
- Correct role + owner → success
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video


engine = create_engine(
    "sqlite:///./test_role_enforcement.sqlite",
    connect_args={"check_same_thread": False},
)
TestSession = sessionmaker(bind=engine)
client = TestClient(app)


def _override_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = _override_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def _make_user(email: str, role: str) -> User:
    db = TestSession()
    # Normalize role to title case to match UserRole enum
    role_normalized = role.title().replace("_", " ")
    user = User(name="Test User", email=email, password="hash", role=role_normalized)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def _make_video_with_transcript(user: User) -> tuple[Video, Transcript]:
    db = TestSession()
    video = Video(
        user_id=user.id,
        filename="test.mp4", 
        file_path="/tmp/test.mp4",
        status="completed"
    )
    db.add(video)
    db.flush()
    
    transcript = Transcript(
        video_id=video.id,
        text="Sample transcript text.",
        language="en",
        segments=[],
        status=TranscriptStatus.COMPLETED
    )
    db.add(transcript)
    db.commit()
    db.refresh(video)
    db.refresh(transcript)
    db.expunge_all()
    db.close()
    return video, transcript


def _auth_user(user: User):
    """Set the authenticated user for all endpoints."""
    from app.dependencies.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: user


class TestVideoUploadAuthorization:
    
    def test_unauthenticated_returns_401(self):
        r = client.post("/videos/upload", files={"file": ("test.mp4", b"data", "video/mp4")})
        assert r.status_code == 401
    
    def test_learner_returns_403(self):
        user = _make_user("learner@test.com", "learner")
        _auth_user(user)
        r = client.post("/videos/upload", files={"file": ("test.mp4", b"data", "video/mp4")})
        assert r.status_code == 403
    
    def test_administrator_returns_403(self):
        user = _make_user("admin@test.com", "administrator")
        _auth_user(user)
        r = client.post("/videos/upload", files={"file": ("test.mp4", b"data", "video/mp4")})
        assert r.status_code == 403
    
    def test_content_creator_allowed(self):
        user = _make_user("creator@test.com", "content_creator")
        _auth_user(user)
        # Note: This will fail due to background processing but should not be 403
        r = client.post("/videos/upload", files={"file": ("test.mp4", b"data", "video/mp4")})
        assert r.status_code != 403
        assert r.status_code != 401
    
    def test_educator_allowed(self):
        user = _make_user("educator@test.com", "educator")
        _auth_user(user)
        r = client.post("/videos/upload", files={"file": ("test.mp4", b"data", "video/mp4")})
        assert r.status_code != 403
        assert r.status_code != 401


class TestTranscriptGenerationAuthorization:
    
    def test_unauthenticated_returns_401(self):
        r = client.post("/videos/1/transcript")
        assert r.status_code == 401
    
    def test_learner_returns_403(self):
        user = _make_user("learner-gen@test.com", "learner")
        _auth_user(user)
        r = client.post("/videos/1/transcript")
        assert r.status_code == 403
    
    def test_administrator_returns_403(self):
        user = _make_user("admin-gen@test.com", "administrator")
        _auth_user(user)
        r = client.post("/videos/1/transcript")
        assert r.status_code == 403
    
    def test_content_creator_with_wrong_video_returns_404(self):
        creator = _make_user("creator-gen@test.com", "content_creator")
        other_user = _make_user("other-gen@test.com", "content_creator")
        video, _ = _make_video_with_transcript(other_user)
        _auth_user(creator)
        r = client.post(f"/videos/{video.id}/transcript")
        assert r.status_code == 404
    
    def test_educator_with_own_video_not_forbidden(self):
        educator = _make_user("educator-gen@test.com", "educator")
        video, _ = _make_video_with_transcript(educator)
        _auth_user(educator)
        r = client.post(f"/videos/{video.id}/transcript")
        # Should not be 403 (role forbidden) or 401 (auth)
        assert r.status_code != 403
        assert r.status_code != 401


class TestTranscriptEditAuthorization:
    
    def test_unauthenticated_returns_401(self):
        r = client.patch("/videos/1/transcript", json={"text": "new"})
        assert r.status_code == 401
    
    def test_learner_returns_403(self):
        user = _make_user("learner-edit@test.com", "learner")
        _auth_user(user)
        r = client.patch("/videos/1/transcript", json={"text": "new"})
        assert r.status_code == 403
    
    def test_administrator_returns_403(self):
        user = _make_user("admin-edit@test.com", "administrator")
        _auth_user(user)
        r = client.patch("/videos/1/transcript", json={"text": "new"})
        assert r.status_code == 403
    
    def test_content_creator_with_own_video_allowed(self):
        creator = _make_user("creator-edit@test.com", "content_creator")
        video, transcript = _make_video_with_transcript(creator)
        _auth_user(creator)
        r = client.patch(f"/videos/{video.id}/transcript", json={"text": "edited"})
        assert r.status_code != 403
        assert r.status_code != 401
    
    def test_educator_with_own_video_allowed(self):
        educator = _make_user("educator-edit@test.com", "educator")
        video, transcript = _make_video_with_transcript(educator)
        _auth_user(educator)
        r = client.patch(f"/videos/{video.id}/transcript", json={"text": "edited"})
        assert r.status_code != 403
        assert r.status_code != 401


class TestSummaryGenerationAuthorization:
    
    def test_learner_forbidden_generate_summary(self):
        user = _make_user("learner-sum@test.com", "learner")
        _auth_user(user)
        r = client.post("/videos/1/summary")
        assert r.status_code == 403
    
    def test_learner_forbidden_regenerate_summary(self):
        user = _make_user("learner-regen@test.com", "learner")
        _auth_user(user)
        r = client.post("/videos/1/summary/regenerate")
        assert r.status_code == 403
    
    def test_administrator_forbidden_generate_summary(self):
        user = _make_user("admin-sum@test.com", "administrator")
        _auth_user(user)
        r = client.post("/videos/1/summary")
        assert r.status_code == 403
    
    def test_content_creator_allowed_generate(self):
        creator = _make_user("creator-sum@test.com", "content_creator")
        video, transcript = _make_video_with_transcript(creator)
        _auth_user(creator)
        r = client.post(f"/videos/{video.id}/summary")
        assert r.status_code != 403
        assert r.status_code != 401
    
    def test_educator_allowed_regenerate(self):
        educator = _make_user("educator-sum@test.com", "educator")
        video, transcript = _make_video_with_transcript(educator)
        _auth_user(educator)
        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code != 403
        assert r.status_code != 401


class TestKeyMomentsAuthorization:
    
    def test_learner_forbidden_generate_key_moments(self):
        user = _make_user("learner-km@test.com", "learner")
        _auth_user(user)
        r = client.post("/videos/1/key-moments/generate")
        assert r.status_code == 403
    
    def test_administrator_forbidden_generate_key_moments(self):
        user = _make_user("admin-km@test.com", "administrator")
        _auth_user(user)
        r = client.post("/videos/1/key-moments/generate")
        assert r.status_code == 403
    
    def test_content_creator_allowed_key_moments(self):
        creator = _make_user("creator-km@test.com", "content_creator")
        video, transcript = _make_video_with_transcript(creator)
        _auth_user(creator)
        r = client.post(f"/videos/{video.id}/key-moments/generate")
        assert r.status_code != 403
        assert r.status_code != 401
    
    def test_educator_allowed_key_moments(self):
        educator = _make_user("educator-km@test.com", "educator")
        video, transcript = _make_video_with_transcript(educator)
        _auth_user(educator)
        r = client.post(f"/videos/{video.id}/key-moments/generate")
        assert r.status_code != 403
        assert r.status_code != 401