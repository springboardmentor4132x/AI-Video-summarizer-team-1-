"""Unit and integration tests for Analytics routes and calculation service."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import create_access_token, get_password_hash
from app.db.session import Base, get_db
from app.main import app
from app.models.key_moment import KeyMoment
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video


TEST_DATABASE_URL = "sqlite:///./test_analytics.sqlite"
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
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


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def setup_analytics_data(db_session):
    creator1 = User(
        name="Creator One",
        email="creator1_test@clipmind.ai",
        password=get_password_hash("password123"),
        role="Content Creator",
    )
    creator2 = User(
        name="Creator Two",
        email="creator2_test@clipmind.ai",
        password=get_password_hash("password123"),
        role="Content Creator",
    )
    learner = User(
        name="Learner One",
        email="learner1_test@clipmind.ai",
        password=get_password_hash("password123"),
        role="Learner",
    )
    admin = User(
        name="Admin User",
        email="admin1_test@clipmind.ai",
        password=get_password_hash("password123"),
        role="Administrator",
    )

    db_session.add_all([creator1, creator2, learner, admin])
    db_session.commit()
    db_session.refresh(creator1)
    db_session.refresh(creator2)
    db_session.refresh(learner)
    db_session.refresh(admin)

    # Videos for Creator 1
    v1 = Video(user_id=creator1.id, filename="creator1_video1.mp4", file_path="/fake/v1.mp4", status="completed")
    v2 = Video(user_id=creator1.id, filename="creator1_video2.mp4", file_path="/fake/v2.mp4", status="processing")
    # Video for Creator 2
    v3 = Video(user_id=creator2.id, filename="creator2_video1.mp4", file_path="/fake/v3.mp4", status="completed")

    db_session.add_all([v1, v2, v3])
    db_session.commit()
    db_session.refresh(v1)
    db_session.refresh(v2)
    db_session.refresh(v3)

    # Transcripts
    t1 = Transcript(
        video_id=v1.id,
        text="This is an introduction to artificial intelligence and deep neural networks in modern software.",
        status=TranscriptStatus.COMPLETED,
    )
    t3 = Transcript(
        video_id=v3.id,
        text="Quantum computing and cryptographic principles for secure communications.",
        status=TranscriptStatus.COMPLETED,
    )
    db_session.add_all([t1, t3])
    db_session.commit()
    db_session.refresh(t1)
    db_session.refresh(t3)

    # Summaries
    s1 = Summary(
        transcript_id=t1.id,
        short_summary="AI and neural networks summary.",
        detailed_summary="Detailed analysis of AI architectures and modern deep neural networks.",
        status=SummaryStatus.COMPLETED,
    )
    db_session.add(s1)
    db_session.commit()

    # Key moments
    km1 = KeyMoment(
        video_id=v1.id,
        start_time=0.0,
        end_time=30.0,
        title="Introduction to AI",
        topic="artificial intelligence",
        importance_score=0.92,
        text="AI overview",
    )
    km2 = KeyMoment(
        video_id=v1.id,
        start_time=30.0,
        end_time=60.0,
        title="Deep Neural Networks",
        topic="neural networks",
        importance_score=0.85,
        text="Neural networks discussion",
    )
    db_session.add_all([km1, km2])
    db_session.commit()

    return {
        "creator1": creator1,
        "creator2": creator2,
        "learner": learner,
        "admin": admin,
        "v1": v1,
        "v2": v2,
        "v3": v3,
    }


def test_creator_analytics_authorization_and_scoping(setup_analytics_data):
    creator1 = setup_analytics_data["creator1"]
    token = create_access_token(subject=str(creator1.id))

    response = client.get("/analytics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()

    assert data["overview"]["total_videos"] == 2
    assert data["overview"]["completed_videos"] == 1
    assert data["overview"]["processing_videos"] == 1
    assert data["overview"]["total_transcripts"] == 1
    assert data["overview"]["total_summaries"] == 1
    assert data["overview"]["total_key_moments"] == 2

    # Verify creator 1 cannot see creator 2's videos
    recent_filenames = [v["filename"] for v in data["recent_videos"]]
    assert "creator1_video1.mp4" in recent_filenames
    assert "creator1_video2.mp4" in recent_filenames
    assert "creator2_video1.mp4" not in recent_filenames


def test_creator_cannot_access_admin_analytics(setup_analytics_data):
    creator1 = setup_analytics_data["creator1"]
    token = create_access_token(subject=str(creator1.id))

    response = client.get("/admin/analytics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_learner_cannot_access_analytics(setup_analytics_data):
    learner = setup_analytics_data["learner"]
    token = create_access_token(subject=str(learner.id))

    response = client.get("/analytics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403

    response_admin = client.get("/admin/analytics", headers={"Authorization": f"Bearer {token}"})
    assert response_admin.status_code == 403


def test_admin_can_access_admin_analytics(setup_analytics_data):
    admin = setup_analytics_data["admin"]
    token = create_access_token(subject=str(admin.id))

    response = client.get("/admin/analytics", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    data = response.json()

    assert data["overview"]["total_videos"] == 3
    assert data["overview"]["total_transcripts"] == 2
    assert data["overview"]["total_summaries"] == 1
    assert data["overview"]["total_key_moments"] == 2


def test_date_range_validation(setup_analytics_data):
    admin = setup_analytics_data["admin"]
    token = create_access_token(subject=str(admin.id))

    response = client.get(
        "/admin/analytics?from=2026-12-31&to=2026-01-01",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
