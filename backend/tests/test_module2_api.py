from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.key_moment import KeyMoment
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video
from app.routers import summary as summary_router
from app.services.key_moment_service import detect_key_moments, save_key_moments
from app.services.summarization_service import SummaryResult


engine = create_engine(
    "sqlite:///./test_module2.sqlite",
    connect_args={"check_same_thread": False},
)
TestingSessionLocal = sessionmaker(bind=engine)
client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def create_user(email: str) -> User:
    db = TestingSessionLocal()
    user = User(name="Module Two User", email=email, password="hash", role="learner")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.close()
    return user


def use_database_and_user(user: User):
    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: user


def create_video_data(user: User):
    db = TestingSessionLocal()
    video = Video(
        user_id=user.id,
        filename="module2.mp4",
        storage_key=f"videos/{user.id}/{uuid4()}.mp4",
        mime_type="video/mp4",
        file_size_bytes=10,
        processing_status="COMPLETED",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    transcript = Transcript(
        video_id=video.id,
        text="Python is useful. FastAPI exposes a clean API.",
        language="en",
        segments=[{"start": 0, "end": 5, "text": "Python is useful."}],
        status=TranscriptStatus.COMPLETED,
    )
    db.add(transcript)
    db.commit()
    db.refresh(video)
    db.close()
    return video.id


def test_transcript_and_summary_api_persist_and_return_owned_data(monkeypatch):
    user = create_user("module2-owner@example.com")
    use_database_and_user(user)
    video_id = create_video_data(user)

    transcript_response = client.get(f"/videos/{video_id}/transcript")
    assert transcript_response.status_code == 200
    assert transcript_response.json()["status"] == "COMPLETED"

    monkeypatch.setattr(
        summary_router,
        "summarize_text",
        lambda _text: SummaryResult("Short result", "Detailed result"),
    )
    summary_response = client.post(f"/videos/{video_id}/summary")
    assert summary_response.status_code == 200
    assert summary_response.json()["short_summary"] == "Short result"
    assert summary_response.json()["status"] == "COMPLETED"

    repeat_response = client.post(f"/videos/{video_id}/summary")
    assert repeat_response.status_code == 200
    db = TestingSessionLocal()
    assert db.query(Summary).count() == 1
    db.close()


def test_failed_summary_can_be_retried_without_duplicate(monkeypatch):
    user = create_user("module2-retry@example.com")
    use_database_and_user(user)
    video_id = create_video_data(user)
    attempts = iter([ValueError("temporary failure"), SummaryResult("Retry short", "Retry detailed")])

    def fake_summary(_text):
        attempt = next(attempts)
        if isinstance(attempt, Exception):
            raise attempt
        return attempt

    monkeypatch.setattr(summary_router, "summarize_text", fake_summary)
    first = client.post(f"/videos/{video_id}/summary")
    assert first.status_code == 500

    retry = client.post(f"/videos/{video_id}/summary/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "COMPLETED"

    db = TestingSessionLocal()
    summary = db.query(Summary).one()
    assert summary.status == SummaryStatus.COMPLETED
    db.close()


def test_key_moment_endpoint_filters_by_video_and_reprocessing_is_idempotent():
    user = create_user("module2-moments@example.com")
    use_database_and_user(user)
    video_id = create_video_data(user)
    db = TestingSessionLocal()
    moments = detect_key_moments(
        [{"start": 0, "end": 4, "text": "Python Python API design."}],
        threshold=0,
    )
    save_key_moments(db, video_id, moments)
    db.commit()
    save_key_moments(db, video_id, moments)
    db.commit()
    assert db.query(KeyMoment).filter(KeyMoment.video_id == video_id).count() == len(moments)
    db.close()

    response = client.get(f"/videos/{video_id}/key-moments")
    assert response.status_code == 200
    assert response.json()["status"] == "COMPLETED"
