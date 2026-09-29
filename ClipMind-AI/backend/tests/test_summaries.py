from collections.abc import Generator
import json
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Summary, SummaryStatus, Transcript, TranscriptStatus, Video, VideoProcessingStatus
from app.schemas.summary import GeminiSummaryOutput
from app.services import summary as summary_service
from app.services import gemini as gemini_service
from app.services.storage import get_storage
from app.services.summary import SummaryError, summarize_transcript, summarize_transcript_with_gemini


test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
client = TestClient(app)


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def upload_fileobj(self, fileobj, storage_key: str, mime_type: str) -> None:
        self.files[storage_key] = fileobj.read()

    def download_fileobj(self, storage_key: str, fileobj) -> None:
        fileobj.write(self.files[storage_key])

    def delete_object(self, storage_key: str) -> None:
        self.files.pop(storage_key, None)


fake_storage = FakeStorage()


def mock_gemini_summary(
    monkeypatch,
    *,
    short_summary="The video explains planning.",
    long_summary="The transcript describes the planning process and its main considerations.",
    key_points=None,
    on_request=None,
    error=None,
    response_text=None,
):
    result = {
        "short_summary": short_summary,
        "long_summary": long_summary,
        "key_points": key_points if key_points is not None else ["Planning is the central topic."],
    }

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            if on_request:
                on_request(model, contents, config)
            if error:
                raise error
            return SimpleNamespace(text=response_text if response_text is not None else json.dumps(result))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(summary_service.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(summary_service.genai, "Client", lambda **_kwargs: FakeClient())


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    fake_storage.files.clear()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_storage] = lambda: fake_storage
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_storage, None)


def create_user(role: str, suffix: str) -> str:
    email = f"{suffix}@example.com"
    registration = client.post(
        "/auth/register",
        json={
            "full_name": f"Test {suffix}",
            "email": email,
            "password": "strong-password",
            "confirm_password": "strong-password",
            "role": role,
        },
    )
    assert registration.status_code == 201
    login = client.post("/auth/login", json={"email": email, "password": "strong-password"})
    assert login.status_code == 200
    return login.json()["access_token"]


def create_video(token: str) -> str:
    response = client.post(
        "/videos/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("lesson.mp4", b"video-bytes", "video/mp4")},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_creator_can_generate_summary_from_existing_transcript(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "creator")
    video_id = create_video(creator_token)
    mock_gemini_summary(
        monkeypatch,
        short_summary="The lesson introduces planning and launch strategy.",
        long_summary="The lesson discusses planning, execution, launch strategy, and practical examples.",
        key_points=["Planning supports execution.", "Launch strategy is discussed."],
    )
    monkeypatch.setattr(
        "app.services.transcript.transcribe",
        lambda path: {
            "text": "Welcome to the lesson. We will discuss planning, execution, and launch strategy. This session covers key milestones and practical examples.",
            "segments": [{"start_time": 0.0, "end_time": 3.0, "text": "Welcome to the lesson. We will discuss planning, execution, and launch strategy."}],
            "language": "en",
        },
    )

    transcript_response = client.post(
        f"/videos/{video_id}/transcript",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert transcript_response.status_code == 200

    summary_response = client.post(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert summary_response.status_code == 200
    assert summary_response.json()["overview"] == "The lesson introduces planning and launch strategy."
    assert summary_response.json()["content"] == "The lesson discusses planning, execution, launch strategy, and practical examples."
    assert summary_response.json()["main_points"] == ["Planning supports execution.", "Launch strategy is discussed."]
    assert summary_response.json()["key_takeaways"] == summary_response.json()["main_points"]
    with TestingSessionLocal() as db:
        summary = db.scalar(select(Summary).where(Summary.video_id == UUID(video_id)))
        assert summary is not None
        assert summary.content

    saved_response = client.get(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert saved_response.status_code == 200
    assert saved_response.json()["video_id"] == video_id
    assert saved_response.json()["overview"] == summary_response.json()["overview"]


def test_summary_requires_existing_transcript(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "creator")
    video_id = create_video(creator_token)

    response = client.post(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert response.status_code == 404
    assert "Generate the transcript first" in response.json()["detail"]


def test_failed_summary_can_be_regenerated_without_conflict(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "retry")
    video_id = create_video(creator_token)
    mock_gemini_summary(monkeypatch)
    with TestingSessionLocal() as db:
        transcript = Transcript(
            video_id=UUID(video_id),
            text="The lesson explains planning and execution. The conclusion recommends review and iteration.",
            segments=[{"start_time": 0, "end_time": 5, "text": "The lesson explains planning and execution. The conclusion recommends review and iteration."}],
            status=TranscriptStatus.COMPLETED,
        )
        db.add(transcript)
        db.flush()
        db.add(Summary(
            video_id=UUID(video_id),
            transcript_id=transcript.id,
            content="",
            overview="",
            main_points=[],
            key_takeaways=[],
            status=SummaryStatus.FAILED,
            error_message="Previous summary generation failed.",
        ))
        db.commit()

    with TestingSessionLocal() as db:
        existing_id = db.scalar(select(Summary).where(Summary.video_id == UUID(video_id))).id

    first_response = client.post(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert first_response.status_code == 200
    assert first_response.json()["status"] == "COMPLETED"
    assert first_response.json()["id"] == str(existing_id)

    retry_response = client.post(
        f"/videos/{video_id}/summary/retry",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert retry_response.status_code == 200
    assert retry_response.json()["status"] == "COMPLETED"
    assert retry_response.json()["overview"]
    assert retry_response.json()["error_message"] is None

    regenerate_response = client.post(
        f"/videos/{video_id}/summary?regenerate=true",
        headers={"Authorization": f"Bearer {creator_token}"},
    )
    assert regenerate_response.status_code == 200
    assert regenerate_response.json()["id"] == retry_response.json()["id"]
    assert regenerate_response.json()["status"] == "COMPLETED"


def test_summary_regeneration_updates_existing_completed_record(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "summary-regenerate")
    video_id = create_video(creator_token)
    with TestingSessionLocal() as db:
        video = db.get(Video, UUID(video_id))
        video.processing_status = VideoProcessingStatus.COMPLETED
        db.add(Transcript(
            video_id=UUID(video_id),
            text="The selected transcript describes the original lesson.",
            segments=[{"start_time": 0, "end_time": 3, "text": "The selected transcript describes the original lesson."}],
            status=TranscriptStatus.COMPLETED,
        ))
        db.commit()

    mock_gemini_summary(monkeypatch, short_summary="Original summary.")
    first_response = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})
    first_summary_id = first_response.json()["id"]

    mock_gemini_summary(monkeypatch, short_summary="Regenerated summary.")
    regenerated = client.post(
        f"/videos/{video_id}/summary?regenerate=true",
        headers={"Authorization": f"Bearer {creator_token}"},
    )

    assert first_response.status_code == 200
    assert regenerated.status_code == 200
    assert regenerated.json()["id"] == first_summary_id
    assert regenerated.json()["overview"] == "Regenerated summary."


def test_summary_for_nonexistent_video_returns_not_found() -> None:
    creator_token = create_user("Content Creator", "summary-missing-video")

    response = client.post(
        "/videos/00000000-0000-0000-0000-000000000001/summary",
        headers={"Authorization": f"Bearer {creator_token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Video not found"


def test_non_owner_cannot_generate_summary() -> None:
    owner_token = create_user("Content Creator", "owner")
    other_token = create_user("Content Creator", "other")
    video_id = create_video(owner_token)

    response = client.post(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert response.status_code == 403

    get_response = client.get(
        f"/videos/{video_id}/summary",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert get_response.status_code == 403


def test_summarizer_covers_beginning_middle_and_end_without_duplicate_points() -> None:
    transcript = " ".join([
        "The introduction explains project planning and audience needs.",
        "Planning identifies the main goals and constraints.",
        "The middle section demonstrates the deployment workflow and monitoring strategy.",
        "The workflow uses monitoring to measure reliable results.",
        "The conclusion recommends reviewing results before the next release.",
    ])

    result = summarize_transcript(transcript)

    assert len(result.main_points) >= 3
    assert any("introduction" in point.lower() for point in result.main_points)
    assert any("deployment" in point.lower() for point in result.main_points)
    assert any("conclusion" in point.lower() for point in result.main_points)
    assert len(result.main_points) == len(set(result.main_points))
    assert len(result.overview) < len(transcript)


def test_summary_reuses_existing_record_for_same_video(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "reuse")
    video_id = create_video(creator_token)
    mock_gemini_summary(monkeypatch)
    with TestingSessionLocal() as db:
        db.add(Transcript(
            video_id=UUID(video_id),
            text="The lesson explains planning. The conclusion recommends review.",
            segments=[{"start_time": 0, "end_time": 2, "text": "The lesson explains planning."}],
            status=TranscriptStatus.COMPLETED,
        ))
        db.commit()

    first = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})
    monkeypatch.setattr(summary_service.genai, "Client", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("regenerated")))
    second = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["video_id"] == video_id


def test_gemini_summary_uses_only_the_requested_video_transcript(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "segment-source")
    video_id = create_video(creator_token)
    other_video_id = create_video(creator_token)
    prompts: list[str] = []
    mock_gemini_summary(
        monkeypatch,
        short_summary="The selected video explains solar panels.",
        long_summary="The selected video explains how solar panels work.",
        key_points=["Solar panels are the subject of the selected video."],
        on_request=lambda _model, contents, _config: prompts.append(contents),
    )
    with TestingSessionLocal() as db:
        db.add_all([
            Transcript(
                video_id=UUID(video_id),
                text="Legacy text must not be used instead of selected segments.",
                segments=[{"start_time": 0, "end_time": 2, "text": "The selected video explains solar panels."}],
                status=TranscriptStatus.COMPLETED,
            ),
            Transcript(
                video_id=UUID(other_video_id),
                text="Another video's transcript mentions wind turbines.",
                segments=[{"start_time": 0, "end_time": 2, "text": "Another video explains wind turbines."}],
                status=TranscriptStatus.COMPLETED,
            ),
        ])
        db.commit()

    response = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 200
    assert response.json()["overview"] == "The selected video explains solar panels."
    assert response.json()["content"] == "The selected video explains how solar panels work."
    assert prompts and "The selected video explains solar panels." in prompts[0]
    assert "Legacy text must not be used" not in prompts[0]
    assert "wind turbines" not in prompts[0]


def test_summary_rejects_processing_and_empty_transcripts() -> None:
    creator_token = create_user("Content Creator", "summary-status")
    processing_video_id = create_video(creator_token)
    empty_video_id = create_video(creator_token)
    with TestingSessionLocal() as db:
        db.add_all([
            Transcript(video_id=UUID(processing_video_id), status=TranscriptStatus.PROCESSING),
            Transcript(video_id=UUID(empty_video_id), status=TranscriptStatus.COMPLETED, text="", segments=[]),
        ])
        db.commit()

    processing = client.post(f"/videos/{processing_video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})
    empty = client.post(f"/videos/{empty_video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})

    assert processing.status_code == 409
    assert "still being generated" in processing.json()["detail"]
    assert empty.status_code == 422
    assert "no transcript content" in empty.json()["detail"]


def test_editing_transcript_invalidates_only_that_videos_summary(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "invalidate")
    video_id = create_video(creator_token)
    mock_gemini_summary(
        monkeypatch,
        short_summary="The revised transcript explains deployment.",
        long_summary="The revised transcript discusses deployment.",
        key_points=["Deployment is the revised topic."],
    )
    with TestingSessionLocal() as db:
        db.add(Transcript(
            video_id=UUID(video_id),
            text="The first transcript explains planning.",
            segments=[{"start_time": 0, "end_time": 2, "text": "The first transcript explains planning."}],
            status=TranscriptStatus.COMPLETED,
        ))
        db.commit()

    generated = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})
    assert generated.status_code == 200

    updated = client.patch(
        f"/videos/{video_id}/transcript",
        headers={"Authorization": f"Bearer {creator_token}"},
        json={"text": "The revised transcript explains deployment.", "segments": [{"start_time": 0, "end_time": 2, "text": "The revised transcript explains deployment."}]},
    )
    assert updated.status_code == 200

    missing = client.get(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})
    regenerated = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})

    assert missing.status_code == 404
    assert regenerated.status_code == 200
    assert "deployment" in regenerated.json()["overview"].lower()


def test_gemini_summary_output_validation_rejects_invalid_fields() -> None:
    with pytest.raises(ValidationError):
        GeminiSummaryOutput.model_validate({"short_summary": "", "long_summary": "Details", "key_points": []})
    with pytest.raises(ValidationError):
        GeminiSummaryOutput.model_validate({"short_summary": "Short", "long_summary": "Details", "key_points": [""]})
    with pytest.raises(ValidationError):
        GeminiSummaryOutput.model_validate({"short_summary": "Short", "long_summary": "Details", "key_points": "not a list"})


def test_gemini_summary_rejects_malformed_json_response(monkeypatch) -> None:
    mock_gemini_summary(monkeypatch, response_text="not-json")

    with pytest.raises(SummaryError, match="Gemini summary generation failed"):
        summarize_transcript_with_gemini("The selected transcript text.")


def test_gemini_summary_provider_failure_marks_record_failed_without_fallback(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "gemini-failure")
    video_id = create_video(creator_token)
    mock_gemini_summary(monkeypatch, error=RuntimeError("provider unavailable"))
    with TestingSessionLocal() as db:
        db.add(Transcript(
            video_id=UUID(video_id),
            text="Transcript source text.",
            segments=[{"start_time": 0, "end_time": 2, "text": "Transcript source text."}],
            status=TranscriptStatus.COMPLETED,
        ))
        db.commit()

    response = client.post(f"/videos/{video_id}/summary", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Gemini summary generation failed. Please try again."
    with TestingSessionLocal() as db:
        summary = db.scalar(select(Summary).where(Summary.video_id == UUID(video_id)))
        assert summary is not None
        assert summary.status == SummaryStatus.FAILED
        assert summary.content == ""


def test_gemini_summary_retries_transient_provider_error(monkeypatch) -> None:
    attempts = 0
    delays: list[float] = []
    result = {
        "short_summary": "A grounded short summary.",
        "long_summary": "A grounded long summary from the selected transcript.",
        "key_points": ["The transcript describes its main idea."],
    }

    class FakeModels:
        def generate_content(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise summary_service.genai.errors.ServerError(
                    503,
                    {"error": {"code": 503, "message": "Unavailable", "status": "UNAVAILABLE"}},
                )
            return SimpleNamespace(text=json.dumps(result))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(summary_service.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(summary_service.genai, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(gemini_service.time, "sleep", delays.append)
    monkeypatch.setattr(gemini_service.random, "uniform", lambda _low, _high: 1.0)

    generated = summarize_transcript_with_gemini("The selected transcript describes its main idea.")

    assert generated.short_summary == result["short_summary"]
    assert attempts == 3
    assert delays == [1.0, 2.0]
