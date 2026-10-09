"""Tests for the transcript router: POST, PATCH, and download endpoints.

Follows the same pattern as test_module2.py and test_video.py:
- isolated SQLite database per test run
- autouse fixture that rebuilds the schema and overrides get_db
- monkeypatching of Whisper / FFmpeg helpers so no real I/O happens
"""
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.main import app
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video
from app.routers import transcript as transcript_router


TEST_DATABASE_URL = "sqlite:///./test_transcript_endpoints.sqlite"
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
def setup_db(monkeypatch, tmp_path):
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    # Point the transcript router's UPLOAD_DIR at tmp_path so audio stubs land
    # inside the isolated test directory.
    monkeypatch.setattr(transcript_router, "UPLOAD_DIR", tmp_path / "uploads")
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_user(email: str = "user@example.com") -> User:
    db = TestingSessionLocal()
    user = User(name="Test User", email=email, password="hash", role="content creator")
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def _create_video(user: User, file_path: str = "/nonexistent/video.mp4") -> Video:
    db = TestingSessionLocal()
    video = Video(user_id=user.id, filename="video.mp4", file_path=file_path, status="completed")
    db.add(video)
    db.commit()
    db.refresh(video)
    db.expunge(video)
    db.close()
    return video


def _add_transcript(
    video: Video,
    status: TranscriptStatus = TranscriptStatus.COMPLETED,
    text: str = "Hello world.",
    language: str = "en",
    segments: list | None = None,
) -> Transcript:
    db = TestingSessionLocal()
    transcript = Transcript(
        video_id=video.id,
        text=text,
        language=language,
        segments=segments or [{"start": 0.0, "end": 2.0, "text": "Hello world."}],
        status=status,
    )
    db.add(transcript)
    db.commit()
    db.refresh(transcript)
    db.expunge(transcript)
    db.close()
    return transcript


def _use_user(user: User):
    app.dependency_overrides[transcript_router.get_current_user] = lambda: user


def _fake_extraction_ok(audio_path: str):
    """Fake extract_audio that creates a stub .wav file and reports success."""
    def _extract(video_path: str, audio_path: str):
        Path(audio_path).parent.mkdir(parents=True, exist_ok=True)
        Path(audio_path).write_bytes(b"audio")
        return SimpleNamespace(status="completed", audio_path=audio_path)
    return _extract


def _fake_transcription_ok():
    return SimpleNamespace(
        status="completed",
        text="Transcribed text.",
        language="en",
        segments=[{"start": 0.0, "end": 3.0, "text": "Transcribed text."}],
    )


# ===========================================================================
# POST /videos/{video_id}/transcript
# ===========================================================================

class TestGenerateTranscript:

    def test_returns_401_without_auth(self):
        response = client.post("/videos/1/transcript")
        assert response.status_code == 401

    def test_returns_404_for_nonexistent_video(self):
        user = _create_user("gen-404@example.com")
        _use_user(user)
        response = client.post("/videos/9999/transcript")
        assert response.status_code == 404
        assert "Video not found" in response.json()["detail"]

    def test_returns_404_for_video_owned_by_another_user(self):
        owner = _create_user("gen-owner@example.com")
        requester = _create_user("gen-requester@example.com")
        video = _create_video(owner)
        _use_user(requester)
        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 404

    def test_returns_409_when_video_file_not_on_disk(self):
        user = _create_user("gen-nofile@example.com")
        # file_path points to a path that does not exist
        video = _create_video(user, file_path="/nonexistent/missing.mp4")
        _use_user(user)
        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 409
        assert "not available" in response.json()["detail"].lower()

    def test_returns_409_when_generation_already_in_progress(self, tmp_path):
        user = _create_user("gen-busy@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _add_transcript(video, status=TranscriptStatus.PROCESSING)
        _use_user(user)
        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 409
        assert "in progress" in response.json()["detail"].lower()

    def test_returns_existing_completed_transcript_without_rerunning_whisper(
        self, monkeypatch, tmp_path
    ):
        """A COMPLETED transcript is returned immediately; Whisper is never called."""
        user = _create_user("gen-already@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _add_transcript(video, text="Already done.", status=TranscriptStatus.COMPLETED)
        _use_user(user)

        whisper_called = []
        monkeypatch.setattr(
            transcript_router,
            "transcribe_audio",
            lambda *_: whisper_called.append(1) or _fake_transcription_ok(),
        )

        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"
        assert response.json()["text"] == "Already done."
        assert len(whisper_called) == 0

    def test_generates_transcript_successfully(self, monkeypatch, tmp_path):
        user = _create_user("gen-ok@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _use_user(user)

        monkeypatch.setattr(transcript_router, "extract_audio", _fake_extraction_ok(str(tmp_path)))
        monkeypatch.setattr(transcript_router, "transcribe_audio", lambda _: _fake_transcription_ok())

        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "COMPLETED"
        assert body["text"] == "Transcribed text."
        assert body["language"] == "en"
        assert body["segments"] == [{"start": 0.0, "end": 3.0, "text": "Transcribed text."}]
        assert body["video_id"] == video.id

    def test_persists_transcript_in_database(self, monkeypatch, tmp_path):
        user = _create_user("gen-persist@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _use_user(user)

        monkeypatch.setattr(transcript_router, "extract_audio", _fake_extraction_ok(str(tmp_path)))
        monkeypatch.setattr(transcript_router, "transcribe_audio", lambda _: _fake_transcription_ok())

        client.post(f"/videos/{video.id}/transcript")

        db = TestingSessionLocal()
        saved = db.query(Transcript).filter(Transcript.video_id == video.id).one()
        db.close()
        assert saved.status == TranscriptStatus.COMPLETED
        assert saved.text == "Transcribed text."

    def test_cleans_up_audio_file_after_success(self, monkeypatch, tmp_path):
        user = _create_user("gen-cleanup@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _use_user(user)

        monkeypatch.setattr(transcript_router, "extract_audio", _fake_extraction_ok(str(tmp_path)))
        monkeypatch.setattr(transcript_router, "transcribe_audio", lambda _: _fake_transcription_ok())

        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 200
        # No .wav files should be left in the uploads directory.
        upload_dir = tmp_path / "uploads"
        wav_files = list(upload_dir.glob("*_transcription.wav")) if upload_dir.exists() else []
        assert wav_files == []

    def test_marks_failed_and_returns_500_when_audio_extraction_fails(
        self, monkeypatch, tmp_path
    ):
        user = _create_user("gen-audio-fail@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _use_user(user)

        monkeypatch.setattr(
            transcript_router,
            "extract_audio",
            lambda video_path, audio_path: SimpleNamespace(
                status="failed", audio_path=None, error_code="ffmpeg_failed"
            ),
        )

        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 500

        db = TestingSessionLocal()
        saved = db.query(Transcript).filter(Transcript.video_id == video.id).first()
        db.close()
        assert saved is not None
        assert saved.status == TranscriptStatus.FAILED

    def test_marks_failed_and_returns_500_when_whisper_fails(
        self, monkeypatch, tmp_path
    ):
        user = _create_user("gen-whisper-fail@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _use_user(user)

        monkeypatch.setattr(transcript_router, "extract_audio", _fake_extraction_ok(str(tmp_path)))
        monkeypatch.setattr(
            transcript_router,
            "transcribe_audio",
            lambda _: SimpleNamespace(status="failed", error_code="transcription_failed"),
        )

        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 500

        db = TestingSessionLocal()
        saved = db.query(Transcript).filter(Transcript.video_id == video.id).first()
        db.close()
        assert saved is not None
        assert saved.status == TranscriptStatus.FAILED

    def test_retries_failed_transcript(self, monkeypatch, tmp_path):
        """A previously FAILED transcript should be retried on the next POST."""
        user = _create_user("gen-retry@example.com")
        video_file = tmp_path / "video.mp4"
        video_file.write_bytes(b"video")
        video = _create_video(user, file_path=str(video_file))
        _add_transcript(video, status=TranscriptStatus.FAILED, text=None)
        _use_user(user)

        monkeypatch.setattr(transcript_router, "extract_audio", _fake_extraction_ok(str(tmp_path)))
        monkeypatch.setattr(transcript_router, "transcribe_audio", lambda _: _fake_transcription_ok())

        response = client.post(f"/videos/{video.id}/transcript")
        assert response.status_code == 200
        assert response.json()["status"] == "COMPLETED"


# ===========================================================================
# PATCH /videos/{video_id}/transcript
# ===========================================================================

class TestUpdateTranscript:

    def test_returns_401_without_auth(self):
        response = client.patch("/videos/1/transcript", json={"text": "new"})
        assert response.status_code == 401

    def test_returns_404_for_nonexistent_video(self):
        user = _create_user("patch-404video@example.com")
        _use_user(user)
        response = client.patch("/videos/9999/transcript", json={"text": "new"})
        assert response.status_code == 404
        assert "Video not found" in response.json()["detail"]

    def test_returns_404_when_no_transcript_exists(self):
        user = _create_user("patch-notranscript@example.com")
        video = _create_video(user)
        _use_user(user)
        response = client.patch(f"/videos/{video.id}/transcript", json={"text": "new"})
        assert response.status_code == 404
        assert "Transcript not found" in response.json()["detail"]

    def test_returns_404_for_video_owned_by_another_user(self):
        owner = _create_user("patch-owner@example.com")
        requester = _create_user("patch-requester@example.com")
        video = _create_video(owner)
        _add_transcript(video)
        _use_user(requester)
        response = client.patch(f"/videos/{video.id}/transcript", json={"text": "new"})
        assert response.status_code == 404

    def test_returns_409_for_non_completed_transcript(self):
        user = _create_user("patch-processing@example.com")
        video = _create_video(user)
        _add_transcript(video, status=TranscriptStatus.PROCESSING)
        _use_user(user)
        response = client.patch(f"/videos/{video.id}/transcript", json={"text": "new"})
        assert response.status_code == 409
        assert "completed" in response.json()["detail"].lower()

    def test_updates_text_successfully(self):
        user = _create_user("patch-ok@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Original text.")
        _use_user(user)

        response = client.patch(
            f"/videos/{video.id}/transcript",
            json={"text": "Updated text."},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["text"] == "Updated text."
        assert body["status"] == "COMPLETED"

    def test_persists_updated_text_in_database(self):
        user = _create_user("patch-persist@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Before.")
        _use_user(user)

        client.patch(f"/videos/{video.id}/transcript", json={"text": "After."})

        db = TestingSessionLocal()
        saved = db.query(Transcript).filter(Transcript.video_id == video.id).one()
        db.close()
        assert saved.text == "After."

    def test_preserves_segments_when_only_text_is_updated(self):
        original_segments = [{"start": 0.0, "end": 5.0, "text": "Hello."}]
        user = _create_user("patch-preserve@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Old text.", segments=original_segments)
        _use_user(user)

        response = client.patch(
            f"/videos/{video.id}/transcript",
            json={"text": "New text."},
        )
        assert response.status_code == 200
        assert response.json()["segments"] == original_segments

    def test_preserves_language_when_only_text_is_updated(self):
        user = _create_user("patch-lang@example.com")
        video = _create_video(user)
        _add_transcript(video, language="fr")
        _use_user(user)

        response = client.patch(
            f"/videos/{video.id}/transcript",
            json={"text": "Le texte."},
        )
        assert response.status_code == 200
        assert response.json()["language"] == "fr"

    def test_empty_payload_changes_nothing(self):
        user = _create_user("patch-empty@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Unchanged.")
        _use_user(user)

        response = client.patch(f"/videos/{video.id}/transcript", json={})
        assert response.status_code == 200
        assert response.json()["text"] == "Unchanged."

    def test_response_shape_matches_get_endpoint(self):
        """PATCH must return every field that GET returns."""
        user = _create_user("patch-shape@example.com")
        video = _create_video(user)
        _add_transcript(video)
        _use_user(user)

        patch_response = client.patch(
            f"/videos/{video.id}/transcript",
            json={"text": "New value."},
        )
        get_response = client.get(f"/videos/{video.id}/transcript")

        assert patch_response.status_code == 200
        assert get_response.status_code == 200
        patch_body = patch_response.json()
        get_body = get_response.json()
        # Both responses must have the same top-level keys.
        assert set(patch_body.keys()) == set(get_body.keys())


# ===========================================================================
# GET /videos/{video_id}/transcript/download
# ===========================================================================

class TestDownloadTranscript:

    def test_returns_401_without_auth(self):
        response = client.get("/videos/1/transcript/download")
        assert response.status_code == 401

    def test_returns_404_for_nonexistent_video(self):
        user = _create_user("dl-404video@example.com")
        _use_user(user)
        response = client.get("/videos/9999/transcript/download")
        assert response.status_code == 404
        assert "Video not found" in response.json()["detail"]

    def test_returns_404_when_no_transcript_exists(self):
        user = _create_user("dl-notranscript@example.com")
        video = _create_video(user)
        _use_user(user)
        response = client.get(f"/videos/{video.id}/transcript/download")
        assert response.status_code == 404
        assert "Transcript not found" in response.json()["detail"]

    def test_returns_404_for_video_owned_by_another_user(self):
        owner = _create_user("dl-owner@example.com")
        requester = _create_user("dl-requester@example.com")
        video = _create_video(owner)
        _add_transcript(video)
        _use_user(requester)
        response = client.get(f"/videos/{video.id}/transcript/download")
        assert response.status_code == 404

    def test_returns_409_when_transcript_not_completed(self):
        user = _create_user("dl-processing@example.com")
        video = _create_video(user)
        _add_transcript(video, status=TranscriptStatus.PROCESSING)
        _use_user(user)
        response = client.get(f"/videos/{video.id}/transcript/download")
        assert response.status_code == 409

    def test_returns_200_with_plain_text_content_type(self):
        user = _create_user("dl-ok@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Download me.")
        _use_user(user)

        response = client.get(f"/videos/{video.id}/transcript/download")
        assert response.status_code == 200
        assert "text/plain" in response.headers["content-type"]

    def test_response_body_matches_transcript_text(self):
        user = _create_user("dl-content@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Exact transcript content.")
        _use_user(user)

        response = client.get(f"/videos/{video.id}/transcript/download")
        assert response.status_code == 200
        assert response.text == "Exact transcript content."

    def test_content_disposition_is_attachment_with_txt_filename(self):
        user = _create_user("dl-disposition@example.com")
        video = _create_video(user)
        _add_transcript(video, text="Some text.")
        _use_user(user)

        response = client.get(f"/videos/{video.id}/transcript/download")
        disposition = response.headers.get("content-disposition", "")
        assert "attachment" in disposition
        assert "transcript.txt" in disposition

    def test_empty_text_returns_empty_body_not_error(self):
        """A transcript with no text should still return 200 with empty body."""
        user = _create_user("dl-empty@example.com")
        video = _create_video(user)
        _add_transcript(video, text=None)
        _use_user(user)

        response = client.get(f"/videos/{video.id}/transcript/download")
        assert response.status_code == 200
        assert response.text == ""
