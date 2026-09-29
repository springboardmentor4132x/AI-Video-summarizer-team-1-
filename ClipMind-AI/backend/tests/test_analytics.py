from collections.abc import Generator
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth.jwt import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models import KeyMoment, Summary, SummaryStatus, Transcript, TranscriptStatus, User, Video, VideoProcessingStatus
from app.routes import analytics as analytics_routes
from app.schemas.analytics import AnalyticsAIInsights
from app.services import analytics_ai
from app.services import gemini as gemini_service


test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSessionLocal = sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)
client = TestClient(app)


def override_get_db() -> Generator[Session, None, None]:
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function() -> None:
    app.dependency_overrides[get_db] = override_get_db
    Base.metadata.create_all(test_engine)


def teardown_function() -> None:
    Base.metadata.drop_all(test_engine)
    app.dependency_overrides.pop(get_db, None)


def create_user(role: str, suffix: str) -> User:
    with TestingSessionLocal() as db:
        user = User(
            full_name=f"Analytics {suffix}",
            email=f"analytics-{suffix}@example.com",
            password_hash="test-hash",
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


def auth_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_analytics_requires_authentication_and_admin_role() -> None:
    assert client.get("/admin/analytics").status_code == 401

    creator = create_user("Content Creator", "creator")
    response = client.get("/admin/analytics", headers=auth_header(creator))

    assert response.status_code == 403

    learner = create_user("Learner", "learner")
    assert client.get("/analytics", headers=auth_header(learner)).status_code == 403


def test_empty_analytics_response_is_complete() -> None:
    administrator = create_user("Administrator", "empty-admin")

    response = client.get("/admin/analytics", headers=auth_header(administrator))

    assert response.status_code == 200
    data = response.json()
    assert data["overview"]["total_videos"] == 0
    assert data["overview"]["total_duration_seconds"] == 0
    assert data["summary_reports"]["generation_rate_percentage"] == 0
    assert data["content_insights"]["top_keywords"] == []
    assert {"overview", "video_analytics", "summary_reports", "content_insights", "key_moment_analytics", "usage"}.issubset(data)


def test_key_moment_video_groups_include_unique_ids_for_duplicate_filenames() -> None:
    administrator = create_user("Administrator", "duplicate-video-filenames")
    video_ids = []
    with TestingSessionLocal() as db:
        for index in range(2):
            video = Video(
                user_id=administrator.id,
                filename="video-1062668a2c_std.mp4",
                storage_key=f"videos/{uuid4()}.mp4",
                mime_type="video/mp4",
                file_size_bytes=10,
                processing_status=VideoProcessingStatus.COMPLETED,
            )
            db.add(video)
            db.flush()
            video_ids.append(str(video.id))
            db.add(KeyMoment(
                video_id=video.id,
                start_time=float(index * 10),
                end_time=float(index * 10 + 5),
                title=f"Moment {index}",
                topic="analytics",
                description="A duplicate filename test moment",
                importance_score=0.8,
                transcript_text="analytics",
            ))
        db.commit()

    response = client.get("/admin/analytics", headers=auth_header(administrator))

    assert response.status_code == 200
    video_groups = response.json()["key_moment_analytics"]["by_video"]
    assert len(video_groups) == 2
    assert {item["video_id"] for item in video_groups} == set(video_ids)
    assert {item["label"] for item in video_groups} == {"video-1062668a2c_std.mp4"}


def test_creator_analytics_is_scoped_to_the_authenticated_owner() -> None:
    creator = create_user("Content Creator", "owner")
    other_creator = create_user("Content Creator", "other")
    with TestingSessionLocal() as db:
        for user, filename in ((creator, "owned.mp4"), (other_creator, "other.mp4")):
            video = Video(
                user_id=user.id,
                filename=filename,
                storage_key=f"videos/{uuid4()}.mp4",
                mime_type="video/mp4",
                file_size_bytes=10,
                duration_seconds=90,
                processing_status=VideoProcessingStatus.COMPLETED,
            )
            db.add(video)
            db.flush()
            transcript = Transcript(video_id=video.id, text=f"{filename} Python content", status=TranscriptStatus.COMPLETED)
            db.add(transcript)
            db.flush()
            db.add(Summary(
                video_id=video.id,
                transcript_id=transcript.id,
                content="Summary",
                overview="Overview",
                status=SummaryStatus.COMPLETED,
            ))
        db.commit()

    response = client.get("/analytics", headers=auth_header(creator))

    assert response.status_code == 200
    data = response.json()
    assert data["overview"]["total_videos"] == 1
    assert data["overview"]["total_users"] == 0
    assert data["summary_reports"]["total_summaries"] == 1
    assert [item["filename"] for item in data["video_analytics"]["recent_videos"]] == ["owned.mp4"]
    assert data["video_analytics"]["upload_activity"][0]["count"] == 1


def test_analytics_aggregates_existing_records_without_writing() -> None:
    administrator = create_user("Administrator", "data-admin")
    with TestingSessionLocal() as db:
        completed = Video(
            user_id=administrator.id,
            filename="analytics.mp4",
            storage_key=f"videos/{uuid4()}.mp4",
            mime_type="video/mp4",
            file_size_bytes=10,
            duration_seconds=120,
            processing_status=VideoProcessingStatus.COMPLETED,
        )
        failed = Video(
            user_id=administrator.id,
            filename="failed.mp4",
            storage_key=f"videos/{uuid4()}.mp4",
            mime_type="video/mp4",
            file_size_bytes=10,
            duration_seconds=60,
            processing_status=VideoProcessingStatus.FAILED,
        )
        db.add_all([completed, failed])
        db.flush()
        transcript = Transcript(
            video_id=completed.id,
            text="Python Python analytics PostgreSQL",
            status=TranscriptStatus.COMPLETED,
        )
        db.add(transcript)
        db.flush()
        db.add(Summary(
            video_id=completed.id,
            transcript_id=transcript.id,
            content="A stored summary",
            overview="Analytics overview",
            status=SummaryStatus.COMPLETED,
        ))
        db.add(KeyMoment(
            video_id=completed.id,
            start_time=10,
            end_time=25,
            title="Important point",
            topic="analytics",
            description="A useful point",
            importance_score=0.9,
            transcript_text="Important point",
        ))
        db.commit()
        before_counts = (db.query(Video).count(), db.query(Summary).count(), db.query(KeyMoment).count())

    response = client.get("/admin/analytics", headers=auth_header(administrator))

    with TestingSessionLocal() as db:
        after_counts = (db.query(Video).count(), db.query(Summary).count(), db.query(KeyMoment).count())

    assert response.status_code == 200
    data = response.json()
    assert data["overview"]["total_videos"] == 2
    assert data["overview"]["completed_videos"] == 1
    assert data["overview"]["failed_videos"] == 1
    assert data["overview"]["total_duration_seconds"] == 180
    assert data["summary_reports"]["completed_summaries"] == 1
    assert data["summary_reports"]["videos_with_summaries"] == 1
    assert data["content_insights"]["top_keywords"][0] == {"keyword": "python", "count": 2, "frequency": 2, "rank": 1}
    assert data["key_moment_analytics"]["total_key_moments"] == 1
    assert data["key_moment_analytics"]["total_duration_seconds"] == 15
    assert before_counts == after_counts


def test_date_filter_fills_missing_calendar_dates_and_rejects_invalid_ranges() -> None:
    administrator = create_user("Administrator", "dates-admin")
    with TestingSessionLocal() as db:
        db.add(Video(
            user_id=administrator.id,
            filename="dated.mp4",
            storage_key=f"videos/{uuid4()}.mp4",
            mime_type="video/mp4",
            file_size_bytes=10,
            duration_seconds=20,
            processing_status=VideoProcessingStatus.COMPLETED,
            uploaded_at=datetime(2026, 9, 2, 12, tzinfo=timezone.utc),
        ))
        db.commit()

    response = client.get("/admin/analytics?from=2026-09-01&to=2026-09-03", headers=auth_header(administrator))
    invalid = client.get("/admin/analytics?from=2026-09-04&to=2026-09-03", headers=auth_header(administrator))

    assert response.status_code == 200
    assert response.json()["video_analytics"]["upload_activity"] == [
        {"date": "2026-09-01", "count": 0},
        {"date": "2026-09-02", "count": 1},
        {"date": "2026-09-03", "count": 0},
    ]
    assert invalid.status_code == 422


def test_transcript_summary_and_key_moment_intelligence_is_returned() -> None:
    administrator = create_user("Administrator", "intelligence-admin")
    with TestingSessionLocal() as db:
        video = Video(
            user_id=administrator.id,
            filename="intelligence.mp4",
            storage_key=f"videos/{uuid4()}.mp4",
            mime_type="video/mp4",
            file_size_bytes=10,
            duration_seconds=60,
            processing_status=VideoProcessingStatus.COMPLETED,
        )
        db.add(video)
        db.flush()
        transcript = Transcript(
            video_id=video.id,
            text="Python café analytics Python",
            status=TranscriptStatus.COMPLETED,
        )
        db.add(transcript)
        db.flush()
        db.add(Summary(
            video_id=video.id,
            transcript_id=transcript.id,
            content="Python summary",
            overview="Useful analytics overview",
            main_points=["Python point"],
            key_takeaways=["Analytics takeaway"],
            status=SummaryStatus.COMPLETED,
        ))
        db.add(KeyMoment(
            video_id=video.id,
            start_time=5,
            end_time=15,
            title="Analytics moment",
            topic="content",
            description="Important content",
            importance_score=0.8,
            transcript_text="Python café analytics",
        ))
        db.commit()

    response = client.get("/admin/analytics", headers=auth_header(administrator))

    assert response.status_code == 200
    data = response.json()
    assert data["transcript_insights"]["total_words"] == 4
    assert data["transcript_insights"]["longest_transcript_words"] == 4
    assert data["summary_insights"]["total_summary_words"] > 0
    assert data["key_moment_insights"]["videos_with_key_moments"] == 1
    assert data["key_moment_insights"]["total_duration_seconds"] == 10
    assert data["recent_activity"]
    assert {event["type"] for event in data["recent_activity"]} >= {"VIDEO_UPLOADED", "TRANSCRIPT_GENERATED", "SUMMARY_GENERATED", "KEY_MOMENTS_DETECTED"}
    assert 0 <= data["intelligence_score"]["score"] <= 100
    assert len(data["intelligence_score"]["components"]) == 5
    assert data["top_topics"][0]["frequency"] > 0
    assert data["keyword_intelligence"][0]["video_count"] == 1
    assert data["recent_videos"][0]["ai_score"] > 0
    assert data["recent_videos"][0]["transcript_word_count"] == 4
    assert data["content_activity"]
    assert data["compression_insights"]["average_transcript_words"] > 0
    assert data["compression_insights"]["average_summary_words"] > 0
    assert len(data["importance_distribution"]) == 3


def test_ai_analytics_uses_one_verified_snapshot_and_preserves_exact_metrics(monkeypatch) -> None:
    administrator = create_user("Administrator", "ai-snapshot-admin")
    with TestingSessionLocal() as db:
        uploaded = Video(
            user_id=administrator.id,
            filename="uploaded.mp4",
            storage_key=f"videos/{uuid4()}.mp4",
            mime_type="video/mp4",
            file_size_bytes=10,
            duration_seconds=120,
            processing_status=VideoProcessingStatus.COMPLETED,
            source_type="UPLOAD",
        )
        youtube = Video(
            user_id=administrator.id,
            filename="youtube.mp4",
            storage_key=f"videos/{uuid4()}.mp4",
            mime_type="video/mp4",
            file_size_bytes=10,
            duration_seconds=60,
            processing_status=VideoProcessingStatus.FAILED,
            source_type="YOUTUBE",
        )
        db.add_all([uploaded, youtube])
        db.flush()
        transcript = Transcript(
            video_id=uploaded.id,
            text="Python analytics Python insights",
            status=TranscriptStatus.COMPLETED,
        )
        db.add(transcript)
        db.flush()
        db.add(Summary(
            video_id=uploaded.id,
            transcript_id=transcript.id,
            content="Python analytics summary",
            overview="Verified summary",
            status=SummaryStatus.COMPLETED,
        ))
        db.add(KeyMoment(
            video_id=uploaded.id,
            start_time=10,
            end_time=20,
            title="Analytics insight",
            topic="analytics",
            description="Verified key moment",
            importance_score=0.8,
            transcript_text="Python analytics",
        ))
        db.commit()

    generated: dict[str, object] = {}

    class FakeModels:
        def generate_content(self, *, model, contents, config):
            generated["model"] = model
            generated["contents"] = contents
            generated["config"] = config
            return SimpleNamespace(text='''{
              "overview":"The library includes both upload sources.",
              "key_insight":"The file upload completed while the YouTube video failed.",
              "attention":[{"title":"Review failed processing","description":"A video is recorded as failed.","severity":"medium"}],
              "content_insight":"The supplied transcript includes analytics-related terms.",
              "usage_insight":"Activity data is limited to the selected period.",
              "summary_insight":"A completed summary is recorded.",
              "keyword_insight":"Python is the most frequent supplied keyword.",
              "recommendations":["Review the failed video."]
            }''')

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(analytics_ai.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(analytics_ai.genai, "Client", lambda **_kwargs: FakeClient())

    response = client.post("/admin/analytics/ai-insights", headers=auth_header(administrator))

    assert response.status_code == 200
    result = response.json()
    assert result["analytics"]["overview"]["total_videos"] == 2
    assert result["analytics"]["overview"]["completed_videos"] == 1
    assert result["analytics"]["overview"]["failed_videos"] == 1
    assert result["analytics"]["overview"]["uploaded_video_count"] == 1
    assert result["analytics"]["overview"]["youtube_video_count"] == 1
    assert result["analytics"]["overview"]["total_duration_seconds"] == 180
    assert result["analytics"]["summary_reports"]["completed_summaries"] == 1
    assert result["analytics"]["key_moment_analytics"]["total_key_moments"] == 1
    assert result["ai_insights"]["attention"][0]["severity"] == "medium"
    assert generated["model"] == analytics_ai.settings.gemini_model
    assert "VERIFIED ANALYTICS SNAPSHOT:" in generated["contents"]
    assert "uploaded.mp4" not in generated["contents"]
    assert "test-only-key" not in generated["contents"]
    snapshot = json.loads(str(generated["contents"]).split("VERIFIED ANALYTICS SNAPSHOT:\n", 1)[1])
    assert snapshot["total_videos"] == 2
    assert snapshot["completed_videos"] == 1
    assert snapshot["failed_videos"] == 1
    assert snapshot["file_uploads"] == 1
    assert snapshot["youtube_uploads"] == 1
    assert snapshot["transcript_words"] == 4
    assert snapshot["longest_transcript_words"] == 4
    assert snapshot["summaries"] == 1
    assert snapshot["key_moments"] == 1
    assert generated["config"].response_mime_type == "application/json"
    response_schema = json.dumps(generated["config"].response_schema)
    assert "additionalProperties" not in response_schema
    assert "additional_properties" not in response_schema
    assert '"required"' in response_schema
    assert '"enum"' in response_schema


def test_ai_analytics_rejects_invalid_gemini_response_and_keeps_metrics_available(monkeypatch) -> None:
    administrator = create_user("Administrator", "ai-invalid-admin")
    generated: dict[str, str] = {}

    class FakeModels:
        def generate_content(self, *, contents, **_kwargs):
            generated["contents"] = contents
            return SimpleNamespace(text='{"overview":"invalid","unexpected":"field"}')

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(analytics_ai.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(analytics_ai.genai, "Client", lambda **_kwargs: FakeClient())

    ai_response = client.post("/admin/analytics/ai-insights", headers=auth_header(administrator))
    analytics_response = client.get("/admin/analytics", headers=auth_header(administrator))

    assert ai_response.status_code == 503
    assert "analytics data is still available" in ai_response.json()["detail"]
    assert analytics_response.status_code == 200
    assert analytics_response.json()["overview"]["total_videos"] == 0
    snapshot = json.loads(generated["contents"].split("VERIFIED ANALYTICS SNAPSHOT:\n", 1)[1])
    assert snapshot["total_videos"] == 0
    assert snapshot["top_topics"] == []
    assert snapshot["top_keywords"] == []
    assert snapshot["upload_activity"] == []
    assert snapshot["processing_activity"] == []


def test_ai_analytics_provider_failure_returns_friendly_unavailable_response(monkeypatch) -> None:
    administrator = create_user("Administrator", "ai-error-admin")

    class FakeModels:
        def generate_content(self, **_kwargs):
            raise TimeoutError("provider timeout")

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(analytics_ai.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(analytics_ai.genai, "Client", lambda **_kwargs: FakeClient())

    response = client.post("/admin/analytics/ai-insights", headers=auth_header(administrator))

    assert response.status_code == 503
    assert response.json()["detail"] == "AI insights are temporarily unavailable. Your analytics data is still available."


def test_ai_analytics_retries_transient_provider_error(monkeypatch) -> None:
    administrator = create_user("Administrator", "ai-retry-admin")
    attempts = 0
    delays: list[float] = []
    payload = {
        "overview": "The available data provides a broad view.",
        "key_insight": "The leading topic has supporting transcript content.",
        "attention": [],
        "content_insight": "The supplied content is available for review.",
        "usage_insight": "Activity is represented in the selected period.",
        "summary_insight": "Summary coverage can be reviewed alongside transcripts.",
        "keyword_insight": "The leading keyword reflects supplied video content.",
        "recommendations": [],
    }

    class FakeModels:
        def generate_content(self, **_kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise analytics_ai.genai.errors.ServerError(
                    503,
                    {"error": {"code": 503, "message": "Unavailable", "status": "UNAVAILABLE"}},
                )
            return SimpleNamespace(text=json.dumps(payload))

    class FakeClient:
        models = FakeModels()

    monkeypatch.setattr(analytics_ai.settings, "gemini_api_key", "test-only-key")
    monkeypatch.setattr(analytics_ai.genai, "Client", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(gemini_service.time, "sleep", delays.append)
    monkeypatch.setattr(gemini_service.random, "uniform", lambda _low, _high: 1.0)

    response = client.post("/admin/analytics/ai-insights", headers=auth_header(administrator))

    assert response.status_code == 200
    assert response.json()["ai_insights"]["overview"] == payload["overview"]
    assert attempts == 3
    assert delays == [1.0, 2.0]


def test_ai_analytics_endpoint_keeps_existing_access_scopes() -> None:
    creator = create_user("Content Creator", "ai-access-creator")
    learner = create_user("Learner", "ai-access-learner")

    assert client.post("/analytics/ai-insights").status_code == 401
    assert client.post("/admin/analytics/ai-insights", headers=auth_header(creator)).status_code == 403
    assert client.post("/analytics/ai-insights", headers=auth_header(learner)).status_code == 403


def test_ai_insight_schema_rejects_numeric_claims() -> None:
    try:
        AnalyticsAIInsights.model_validate({
            "overview": "There are 17 videos.",
            "key_insight": "The supplied source mix is varied.",
            "attention": [],
            "content_insight": "There is insufficient transcript data.",
            "usage_insight": "There is insufficient activity data.",
            "summary_insight": "There is insufficient summary data.",
            "keyword_insight": "There is insufficient keyword data.",
            "recommendations": [],
        })
    except ValidationError:
        return
    raise AssertionError("Numeric claims should be rejected so Gemini cannot contradict database metrics.")


def test_creator_ai_analytics_snapshot_is_owner_scoped(monkeypatch) -> None:
    creator = create_user("Content Creator", "ai-owner")
    other_creator = create_user("Content Creator", "ai-outsider")
    with TestingSessionLocal() as db:
        for user, filename, source_type in (
            (creator, "owned.mp4", "UPLOAD"),
            (other_creator, "outside.mp4", "YOUTUBE"),
        ):
            db.add(Video(
                user_id=user.id,
                filename=filename,
                storage_key=f"videos/{uuid4()}.mp4",
                mime_type="video/mp4",
                file_size_bytes=10,
                duration_seconds=30,
                source_type=source_type,
                processing_status=VideoProcessingStatus.COMPLETED,
            ))
        db.commit()

    captured: dict[str, object] = {}

    def fake_generate(snapshot):
        captured.update(snapshot)
        return AnalyticsAIInsights(
            overview="The available video has completed processing.",
            key_insight="The available video came from a file upload.",
            attention=[],
            content_insight="There is insufficient transcript data for a content theme.",
            usage_insight="There is insufficient historical activity data.",
            summary_insight="There is insufficient summary data.",
            keyword_insight="There is insufficient keyword data.",
            recommendations=[],
        )

    monkeypatch.setattr(analytics_routes, "generate_analytics_ai_insights", fake_generate)

    response = client.post("/analytics/ai-insights", headers=auth_header(creator))

    assert response.status_code == 200
    assert response.json()["analytics"]["overview"]["total_videos"] == 1
    assert captured["total_videos"] == 1
    assert captured["file_uploads"] == 1
    assert captured["youtube_uploads"] == 0
    assert captured["user_count"] == 0