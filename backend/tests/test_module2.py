from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.summary import Summary, SummaryStatus
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video
from app.routers import key_moment as key_moment_router
from app.routers import summary as summary_router
from app.routers import video as video_router
from app.services.key_moment_service import detect_key_moments


engine = create_engine("sqlite:///./test_module2.sqlite", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_db(monkeypatch, tmp_path):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(video_router, "UPLOAD_DIR", tmp_path / "uploads")
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def create_video(email="module2@example.com", status="uploaded"):
    db = TestingSessionLocal()
    user = User(name="Module 2 User", email=email, password="hash", role="learner")
    db.add(user)
    db.flush()
    video = Video(user_id=user.id, filename="video.mp4", file_path="input.mp4", status=status)
    db.add(video)
    db.commit()
    db.refresh(video)
    user_id = user.id
    video_id = video.id
    db.close()
    return SimpleNamespace(id=user_id), SimpleNamespace(id=video_id)


def use_user(user):
    app.dependency_overrides[video_router.get_current_user] = lambda: user


def test_background_persists_whisper_fields_and_completed_status(monkeypatch, tmp_path):
    user, video = create_video()
    monkeypatch.setattr(video_router, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(video_router, "process_video", lambda **_: True)

    def extract_audio(video_path, audio_path):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"audio")
        return SimpleNamespace(status="completed", audio_path=audio_path)

    monkeypatch.setattr(video_router, "extract_audio", extract_audio)
    monkeypatch.setattr(
        video_router,
        "transcribe_audio",
        lambda _path: SimpleNamespace(
            status="completed",
            text="Stored transcript",
            language="es",
            segments=[{"start": 0.0, "end": 2.0, "text": "Important decision."}],
        ),
    )
    monkeypatch.setattr(video_router, "extract_highlights_for_key_moments", lambda **_: [])

    video_router.process_video_background(video.id, str(tmp_path / "input.mp4"), str(tmp_path / "output.mp4"))

    db = TestingSessionLocal()
    transcript = db.query(Transcript).filter_by(video_id=video.id).one()
    assert transcript.text == "Stored transcript"
    assert transcript.language == "es"
    assert transcript.segments == [{"start": 0.0, "end": 2.0, "text": "Important decision."}]
    assert transcript.status == TranscriptStatus.COMPLETED
    db.close()


def test_background_marks_transcript_failed_when_whisper_fails(monkeypatch, tmp_path):
    user, video = create_video("failed@example.com")
    monkeypatch.setattr(video_router, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(video_router, "process_video", lambda **_: True)
    monkeypatch.setattr(video_router, "extract_audio", lambda **_: SimpleNamespace(status="completed", audio_path="audio.wav"))
    monkeypatch.setattr(video_router, "transcribe_audio", lambda _: SimpleNamespace(status="failed"))

    video_router.process_video_background(video.id, str(tmp_path / "input.mp4"), str(tmp_path / "output.mp4"))

    db = TestingSessionLocal()
    assert db.query(Transcript).filter_by(video_id=video.id).one().status == TranscriptStatus.FAILED
    db.close()


def test_transcript_routes_enforce_ownership_and_return_segments():
    user, video = create_video("route@example.com")
    db = TestingSessionLocal()
    db.add(Transcript(video_id=video.id, text="Text", language="en", segments=[{"start": 1}], status=TranscriptStatus.COMPLETED))
    db.commit()
    db.close()
    use_user(user)

    response = client.get(f"/videos/{video.id}/transcript")
    assert response.status_code == 200
    assert response.json()["segments"] == [{"start": 1}]
    assert client.get(f"/transcripts/{video.id}").status_code == 200


def add_transcript(user, video, status=TranscriptStatus.COMPLETED):
    db = TestingSessionLocal()
    transcript = Transcript(video_id=video.id, text="One sentence. Another detail.", language="en", segments=[], status=status)
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    db.close()
    use_user(user)
    return transcript


def test_summary_requires_completed_transcript():
    user, video = create_video("pending-summary@example.com")
    add_transcript(user, video, TranscriptStatus.PROCESSING)
    response = client.post(f"/videos/{video.id}/summary")
    assert response.status_code == 409


def test_summary_persists_and_does_not_duplicate_completed_result(monkeypatch):
    user, video = create_video("summary@example.com")
    add_transcript(user, video)
    calls = []
    original = summary_router.summarize_transcript
    monkeypatch.setattr(summary_router, "summarize_transcript", lambda transcript: (calls.append(1) or original(transcript)))

    first = client.post(f"/videos/{video.id}/summary")
    second = client.post(f"/videos/{video.id}/summary")
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "COMPLETED"
    assert second.json()["id"] == first.json()["id"]
    assert len(calls) == 1


def test_summary_retry_after_failure(monkeypatch):
    user, video = create_video("retry-summary@example.com")
    add_transcript(user, video)
    attempts = iter([ValueError("local model failed"), None])

    def flaky(_transcript):
        failure = next(attempts)
        if failure:
            raise failure
        return SimpleNamespace(short_summary="short", detailed_summary="detailed")

    monkeypatch.setattr(summary_router, "summarize_transcript", flaky)
    assert client.post(f"/videos/{video.id}/summary").status_code == 500
    assert client.post(f"/videos/{video.id}/summary").json()["status"] == "COMPLETED"


def test_key_moments_use_stored_segments_without_whisper(monkeypatch):
    segments = [{"start": 0.0, "end": 2.0, "text": "Important architecture decision."}]
    monkeypatch.setattr(video_router, "transcribe_audio", lambda *_: (_ for _ in ()).throw(AssertionError("Whisper called")))
    moments = detect_key_moments(segments, threshold=0.3)
    assert moments and moments[0].text == segments[0]["text"]
    assert not hasattr(key_moment_router, "transcribe_audio")