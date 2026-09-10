import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.user import User
from app.models.video import Video
from app.models.transcript import Transcript, TranscriptStatus
from app.models.summary import Summary, SummaryStatus
from app.models.key_moment import KeyMoment
from app.dependencies.auth import get_current_user

engine = create_engine("sqlite:///./test_module2_security.sqlite", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)

def create_user_and_video(email: str, video_id_override=None):
    db = TestingSessionLocal()
    user = User(name="User", email=email, password="hash", role="learner")
    db.add(user)
    db.flush()
    video = Video(user_id=user.id, filename="v.mp4", file_path="v.mp4", status="uploaded")
    if video_id_override:
        video.id = video_id_override
    db.add(video)
    db.flush()
    db.refresh(user)
    db.refresh(video)
    
    transcript = Transcript(video_id=video.id, text="t", status=TranscriptStatus.COMPLETED)
    db.add(transcript)
    db.flush()
    
    summary = Summary(transcript_id=transcript.id, status=SummaryStatus.COMPLETED)
    db.add(summary)
    
    moment = KeyMoment(video_id=video.id, start_time=0.0, end_time=1.0, text="m", title="title", topic="topic", importance_score=0.9)
    db.add(moment)
    
    db.commit()
    user_id = user.id
    video_id = video.id
    transcript_id = transcript.id
    db.close()
    from types import SimpleNamespace
    return SimpleNamespace(id=user_id, role="learner"), SimpleNamespace(id=video_id, transcript_id=transcript_id)

def test_unauthenticated_requests():
    app.dependency_overrides.pop(get_current_user, None)
    
    assert client.get("/transcripts/1").status_code == 401
    assert client.get("/videos/1/transcript").status_code == 401
    assert client.get("/summaries/1").status_code == 401
    assert client.get("/videos/1/summary").status_code == 401
    assert client.post("/videos/1/summary").status_code == 401
    assert client.post("/summaries/1/generate").status_code == 401
    assert client.post("/videos/1/summary/regenerate").status_code == 401
    assert client.get("/videos/1/key-moments").status_code == 401
    assert client.get("/videos/1/highlights/1").status_code == 401

def test_invalid_token():
    app.dependency_overrides.pop(get_current_user, None)
    headers = {"Authorization": "Bearer invalid_token"}
    
    assert client.get("/transcripts/1", headers=headers).status_code == 401

def test_cross_user_access_prevented():
    owner, video = create_user_and_video("owner@example.com", video_id_override=10)
    attacker, _ = create_user_and_video("attacker@example.com")
    
    app.dependency_overrides[get_current_user] = lambda: attacker
    
    # Attempt to access owner's resources
    assert client.get(f"/transcripts/{video.id}").status_code == 404
    assert client.get(f"/videos/{video.id}/transcript").status_code == 404
    assert client.get(f"/summaries/{video.id}").status_code == 404
    assert client.get(f"/videos/{video.id}/summary").status_code == 404
    assert client.post(f"/videos/{video.id}/summary").status_code == 404
    assert client.post(f"/summaries/{video.id}/generate").status_code == 404
    assert client.post(f"/videos/{video.id}/summary/regenerate").status_code == 404
    assert client.get(f"/videos/{video.id}/key-moments").status_code == 404
    assert client.get(f"/videos/{video.id}/highlights/1").status_code == 404

def test_owner_can_access_own_resources():
    owner, video = create_user_and_video("owner2@example.com", video_id_override=20)
    
    app.dependency_overrides[get_current_user] = lambda: owner
    
    assert client.get(f"/transcripts/{video.id}").status_code == 200
    assert client.get(f"/videos/{video.id}/transcript").status_code == 200
    assert client.get(f"/summaries/{video.id}").status_code == 200
    assert client.get(f"/videos/{video.id}/summary").status_code == 200
    assert client.post(f"/videos/{video.id}/summary").status_code == 200
    assert client.post(f"/summaries/{video.id}/generate").status_code == 200
    assert client.post(f"/videos/{video.id}/summary/regenerate").status_code == 200
    assert client.get(f"/videos/{video.id}/key-moments").status_code == 200

def test_duplicate_generation_security():
    owner, video = create_user_and_video("owner3@example.com")
    
    # Change summary status to PROCESSING to test 409
    db = TestingSessionLocal()
    summary = db.query(Summary).filter(Summary.transcript_id == video.transcript_id).first()
    summary.status = SummaryStatus.PROCESSING
    db.commit()
    db.close()
    
    app.dependency_overrides[get_current_user] = lambda: owner
    # Owner gets 409 due to processing status
    assert client.post(f"/videos/{video.id}/summary").status_code == 409
    
    attacker, _ = create_user_and_video("attacker3@example.com")
    app.dependency_overrides[get_current_user] = lambda: attacker
    
    # Attacker gets 404 even though it's processing
    assert client.post(f"/videos/{video.id}/summary").status_code == 404
