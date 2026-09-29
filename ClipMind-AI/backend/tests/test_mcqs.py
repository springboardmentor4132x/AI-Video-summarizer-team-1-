import json
import pytest
from google.genai import errors
from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from google.genai import types

from app.database import Base, get_db
from app.main import app
from app.models import KeyMoment, Summary, Transcript, TranscriptStatus, Video
from app.services import gemini as gemini_service
from app.services import mcq as mcq_service
from app.services.mcq import _validate_and_normalize_mcq
from app.services.storage import get_storage


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


def mock_gemini_mcqs(monkeypatch) -> None:
    class FakeModels:
        def generate_content(self, *, contents, **_kwargs):
            if "beta launch" in contents.lower():
                topic, answer = "Beta launch", "beta launch"
            elif "incident response" in contents.lower():
                topic, answer = "Incident response", "incident response"
            else:
                topic, answer = "Planning strategy", "planning and launch strategy"
            item = {
                "question": f"Which topic does this lesson specifically cover about {topic.lower()}?",
                "options": [answer, "Unrelated production detail", "A different workflow", "An unsupported conclusion"],
                "correct_answer": answer,
                "explanation": f"The selected video's transcript explicitly describes {answer}.",
                "difficulty": "Medium",
                "topic": topic,
                "source": "Transcript",
                "timestamp": "00:00",
            }
            return SimpleNamespace(text=json.dumps([item]))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(mcq_service.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(mcq_service.genai, "Client", lambda **_kwargs: FakeClient())


def override_get_db() -> Session:
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


def test_expected_mcqs_are_generated_from_processed_video_content(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "mcq")
    video_id = create_video(creator_token)
    mock_gemini_mcqs(monkeypatch)

    with TestingSessionLocal() as db:
        transcript = Transcript(
            video_id=UUID(video_id),
            text="The lesson focuses on planning and launch strategy. It also explains review and iteration.",
            segments=[
                {"start_time": 0.0, "end_time": 10.0, "text": "The lesson focuses on planning and launch strategy."},
                {"start_time": 10.0, "end_time": 20.0, "text": "It also explains review and iteration."},
            ],
            status=TranscriptStatus.COMPLETED,
        )
        db.add(transcript)
        db.flush()
        db.add(
            Summary(
                video_id=UUID(video_id),
                transcript_id=transcript.id,
                content="The video focuses on planning and launch strategy.",
                overview="The video focuses on planning and launch strategy.",
                main_points=["Planning", "Launch strategy"],
                key_takeaways=["Execution requires clear planning."],
                status="COMPLETED",
            )
        )
        db.commit()

    response = client.get(f"/videos/{video_id}/mcqs", headers={"Authorization": f"Bearer {creator_token}"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 1
    for item in payload:
        assert item["question"]
        assert len(item["options"]) == 4
        assert item["correct_answer"] in item["options"]
        assert item["explanation"]
        assert item["difficulty"] in {"Easy", "Medium", "Hard"}
        assert item["topic"]
        assert item["source"] in {"Transcript", "Summary", "Key Moment"}
        assert item["question"] not in {"", None}


def test_expected_mcqs_are_specific_to_each_uploaded_video(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "mcq-unique")
    video_a_id = create_video(creator_token)
    video_b_id = create_video(creator_token)
    mock_gemini_mcqs(monkeypatch)

    with TestingSessionLocal() as db:
        for video_id, overview, transcript_text, topic, key_text in [
            (
                UUID(video_a_id),
                "This video explains how the product team plans a beta launch and monitors adoption metrics.",
                "The product team plans the beta launch and tracks adoption metrics after release.",
                "beta launch",
                "Launch readiness depends on clear milestones and measurable adoption.",
            ),
            (
                UUID(video_b_id),
                "This video covers the incident response workflow for production outages and customer communication.",
                "The operations team follows an incident response workflow during production outages and customer communication.",
                "incident response",
                "Support teams coordinate triage, escalation, and customer updates during outages.",
            ),
        ]:
            transcript = Transcript(
                video_id=video_id,
                text=transcript_text,
                segments=[
                    {"start_time": 0.0, "end_time": 8.0, "text": transcript_text},
                ],
                status=TranscriptStatus.COMPLETED,
            )
            db.add(transcript)
            db.flush()
            db.add(
                Summary(
                    video_id=video_id,
                    transcript_id=transcript.id,
                    content=overview,
                    overview=overview,
                    main_points=[topic, "Execution checklist"],
                    key_takeaways=[key_text],
                    status="COMPLETED",
                )
            )
            db.add(
                KeyMoment(
                    video_id=video_id,
                    start_time=12.0,
                    end_time=25.0,
                    title=f"{topic} checkpoint",
                    topic=topic,
                    description=key_text,
                    importance_score=0.9,
                    transcript_text=transcript_text,
                )
            )
        db.commit()

    response_a = client.get(f"/videos/{video_a_id}/mcqs", headers={"Authorization": f"Bearer {creator_token}"})
    response_b = client.get(f"/videos/{video_b_id}/mcqs", headers={"Authorization": f"Bearer {creator_token}"})
    assert response_a.status_code == 200
    assert response_b.status_code == 200

    questions_a = {item["question"] for item in response_a.json()}
    questions_b = {item["question"] for item in response_b.json()}

    assert questions_a != questions_b
    assert any("beta" in item["question"].lower() or "launch" in item["correct_answer"].lower() for item in response_a.json())
    assert any("incident" in item["question"].lower() or "outage" in item["correct_answer"].lower() for item in response_b.json())


def test_validate_and_normalize_accepts_paraphrased_transcript_answer() -> None:
    video = SimpleNamespace(
        transcript=SimpleNamespace(
            text="Git does not use a simple numerical counter for commits. It uses a hash of the changes to identify each commit.",
            segments=[{"start_time": 197.0, "text": "Git does not use a simple numerical counter for commits. It uses a hash of the changes to identify each commit."}],
        ),
        summary=None,
        key_moments=[],
    )
    item = {
        "question": "What does Git use instead of simple natural numbers to identify commits?",
        "options": [
            "A hash of the change itself",
            "A timestamp for each commit",
            "The author’s name",
            "The repository size",
        ],
        "correct_answer": "A hash of the change itself",
        "explanation": "Git identifies commits by hashing the content of the change, not by using a simple incrementing number.",
        "difficulty": "Easy",
        "topic": "Git commit identity",
        "source": "Transcript",
        "timestamp": "03:17",
    }

    result = _validate_and_normalize_mcq(item, video)

    assert result is not None
    assert result["correct_answer"] == "A hash of the change itself"
    assert result["source"] == "Transcript"


def test_validate_and_normalize_rejects_unsupported_answer() -> None:
    video = SimpleNamespace(
        transcript=SimpleNamespace(
            text="Git does not use a simple numerical counter for commits. It uses a hash of the changes to identify each commit.",
            segments=[{"start_time": 197.0, "text": "Git does not use a simple numerical counter for commits. It uses a hash of the changes to identify each commit."}],
        ),
        summary=None,
        key_moments=[],
    )
    item = {
        "question": "What does Git use instead of simple natural numbers to identify commits?",
        "options": [
            "A file count for the repository",
            "A hash of the change itself",
            "The current date",
            "A server log number",
        ],
        "correct_answer": "A file count for the repository",
        "explanation": "This is unsupported by the transcript.",
        "difficulty": "Easy",
        "topic": "Git commit identity",
        "source": "Transcript",
        "timestamp": "03:17",
    }

    assert _validate_and_normalize_mcq(item, video) is None


def test_validate_and_normalize_rejects_malformed_mcq() -> None:
    video = SimpleNamespace(
        transcript=SimpleNamespace(
            text="The lesson explains that a central server maintains the repository history.",
            segments=[{"start_time": 87.0, "text": "The lesson explains that a central server maintains the repository history."}],
        ),
        summary=None,
        key_moments=[],
    )
    item = {
        "question": "Why do centralized systems keep history in one place?",
        "options": [
            "Because of the central server",
            "Because the network is faster",
            "Because users are offline",
        ],
        "correct_answer": "Because of the central server",
        "explanation": "A central server stores the history.",
        "difficulty": "Medium",
        "topic": "Centralized history",
        "source": "Transcript",
        "timestamp": "01:27",
    }

    assert _validate_and_normalize_mcq(item, video) is None


def test_mcq_gemini_client_has_a_finite_request_timeout(monkeypatch) -> None:
    options: dict[str, object] = {}

    def fake_client(**kwargs):
        options.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(mcq_service.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(mcq_service.genai, "Client", fake_client)

    mcq_service._get_gemini_client()

    assert isinstance(options["http_options"], types.HttpOptions)
    assert options["http_options"].timeout == 20_000
    assert options["http_options"].retry_options.attempts == 1


@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_mcq_transient_gemini_errors_retry_four_times_then_return_friendly_503(monkeypatch, status_code: int) -> None:
    creator_token = create_user("Content Creator", f"mcq-transient-{status_code}")
    video_id = create_video(creator_token)
    with TestingSessionLocal() as db:
        db.add(Transcript(
            video_id=UUID(video_id),
            text="The selected lesson describes planning and review.",
            segments=[{"start_time": 0, "end_time": 3, "text": "The selected lesson describes planning and review."}],
            status=TranscriptStatus.COMPLETED,
        ))
        db.commit()

    attempts = 0
    delays: list[float] = []

    class FakeModels:
        def generate_content(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise errors.ServerError(
                status_code,
                {"error": {"code": status_code, "message": "Temporary provider failure", "status": "UNAVAILABLE"}},
            )

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(mcq_service.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(mcq_service.genai, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(gemini_service.time, "sleep", delays.append)
    monkeypatch.setattr(gemini_service.random, "uniform", lambda _low, _high: 1.0)

    response = client.get(f"/videos/{video_id}/mcqs", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Gemini is temporarily unavailable. Please try again shortly."
    assert attempts == 4
    assert delays == [1.0, 2.0, 4.0]


def test_mcq_permanent_gemini_error_is_not_retried(monkeypatch) -> None:
    creator_token = create_user("Content Creator", "mcq-permanent")
    video_id = create_video(creator_token)
    with TestingSessionLocal() as db:
        db.add(Transcript(
            video_id=UUID(video_id),
            text="The selected lesson describes planning and review.",
            segments=[{"start_time": 0, "end_time": 3, "text": "The selected lesson describes planning and review."}],
            status=TranscriptStatus.COMPLETED,
        ))
        db.commit()

    attempts = 0

    class FakeModels:
        def generate_content(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            raise errors.ClientError(400, {"error": {"code": 400, "message": "Bad request", "status": "INVALID_ARGUMENT"}})

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(mcq_service.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(mcq_service.genai, "Client", lambda **_kwargs: FakeClient())

    response = client.get(f"/videos/{video_id}/mcqs", headers={"Authorization": f"Bearer {creator_token}"})

    assert response.status_code == 422
    assert attempts == 1
