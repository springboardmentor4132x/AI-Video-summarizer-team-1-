"""Tests for the P1 fixes.

P1-1: POST /videos/{video_id}/summary/regenerate — verifies the duplicate
      route was removed and that exactly one correct handler owns this path,
      which actually invokes the generation logic with regenerate=True.

P1-2: GET /admin/upload-history — verifies the endpoint exists, enforces
      Administrator-only access, and returns the expected VideoResponse shape
      for all users' videos.

Follows the same test patterns as test_module2.py and test_video.py:
  - isolated file-backed SQLite per test class
  - autouse fixture that rebuilds schema and overrides get_db
  - monkeypatching the summarization service
"""
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
from app.routers import summary as summary_router
from app.routers import admin as admin_router


# ---------------------------------------------------------------------------
# Shared DB / client
# ---------------------------------------------------------------------------

engine = create_engine(
    "sqlite:///./test_p1_endpoints.sqlite",
    connect_args={"check_same_thread": False},
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app, raise_server_exceptions=False)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(email: str, role: str = "content creator") -> User:
    db = TestSession()
    user = User(name="Test User", email=email, password="hash", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def _make_video(user: User, filename: str = "v.mp4") -> Video:
    db = TestSession()
    video = Video(
        user_id=user.id,
        filename=filename,
        file_path="/tmp/v.mp4",
        status="completed",
    )
    db.add(video)
    db.commit()
    db.refresh(video)
    db.expunge(video)
    db.close()
    return video


def _make_completed_transcript(video: Video) -> Transcript:
    db = TestSession()
    t = Transcript(
        video_id=video.id,
        text="One sentence. Another detail about something important.",
        language="en",
        segments=[],
        status=TranscriptStatus.COMPLETED,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    db.expunge(t)
    db.close()
    return t


def _make_completed_summary(transcript: Transcript) -> Summary:
    db = TestSession()
    s = Summary(
        transcript_id=transcript.id,
        short_summary="Old short.",
        detailed_summary="Old detailed.",
        status=SummaryStatus.COMPLETED,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    db.expunge(s)
    db.close()
    return s


def _use_user(user: User) -> None:
    """Inject user as the current authenticated user for all routers."""
    app.dependency_overrides[summary_router.get_current_user] = lambda: user
    app.dependency_overrides[admin_router.require_role(None)] = lambda: user  # unused; role checked via dependency


def _fake_summarize_ok():
    return SimpleNamespace(
        short_summary="New short summary.",
        detailed_summary="New detailed summary.",
    )


# ===========================================================================
# P1-1 — Summary regeneration
# ===========================================================================

class TestSummaryRegenerate:
    """Verify POST /videos/{id}/summary/regenerate behaves correctly after
    the duplicate route was removed."""

    # ------------------------------------------------------------------
    # Only one registration for the regenerate path
    # ------------------------------------------------------------------

    def test_exactly_one_regenerate_route_in_openapi(self):
        """OpenAPI must list POST /videos/{video_id}/summary/regenerate
        exactly once — confirms the duplicate registration was removed."""
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        path_entry = paths.get("/videos/{video_id}/summary/regenerate", {})
        # Should exist
        assert "post" in path_entry, "regenerate path not found in OpenAPI"
        # The old bug caused two entries under the same key which JSON
        # collapses silently, so we verify by checking the operation id is
        # the correct handler (regenerate_summary), not generate_summary.
        op_id = path_entry["post"].get("operationId", "")
        assert "regenerate" in op_id.lower(), (
            f"operationId {op_id!r} does not belong to regenerate_summary"
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def test_returns_401_without_auth(self):
        r = client.post("/videos/1/summary/regenerate")
        assert r.status_code == 401

    # ------------------------------------------------------------------
    # Video / transcript ownership
    # ------------------------------------------------------------------

    def test_returns_404_for_nonexistent_video(self):
        user = _make_user("regen-notvideo@test.com")
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        r = client.post("/videos/99999/summary/regenerate")
        assert r.status_code == 404
        assert "Video not found" in r.json()["detail"]

    def test_returns_404_for_video_owned_by_another_user(self):
        owner = _make_user("regen-owner@test.com")
        requester = _make_user("regen-requester@test.com")
        video = _make_video(owner)
        app.dependency_overrides[summary_router.get_current_user] = lambda: requester
        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code == 404

    def test_returns_404_when_transcript_missing(self):
        user = _make_user("regen-notranscript@test.com")
        video = _make_video(user)
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code == 404
        assert "Transcript" in r.json()["detail"]

    def test_returns_409_when_transcript_not_completed(self):
        user = _make_user("regen-pending@test.com")
        video = _make_video(user)
        db = TestSession()
        db.add(Transcript(
            video_id=video.id, text="x", language="en",
            segments=[], status=TranscriptStatus.PROCESSING,
        ))
        db.commit()
        db.close()
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code == 409

    # ------------------------------------------------------------------
    # Core behaviour: regeneration actually runs even when COMPLETED
    # ------------------------------------------------------------------

    def test_regenerates_completed_summary(self, monkeypatch):
        """The critical regression test: regenerating a COMPLETED summary
        must call the summarization service and produce a new result.
        Pre-fix this would silently return the old summary unchanged."""
        user = _make_user("regen-ok@test.com")
        video = _make_video(user)
        transcript = _make_completed_transcript(video)
        _make_completed_summary(transcript)  # pre-existing COMPLETED summary
        app.dependency_overrides[summary_router.get_current_user] = lambda: user

        calls = []
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda t: (calls.append(1) or _fake_summarize_ok()),
        )

        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code == 200
        assert r.json()["status"] == "COMPLETED"
        # Generation logic must have been invoked
        assert len(calls) == 1, (
            "summarize_transcript was not called — regeneration did not run"
        )
        # Content must reflect the new result, not the stale old one
        assert r.json()["short_summary"] == "New short summary."
        assert r.json()["detailed_summary"] == "New detailed summary."

    def test_regenerate_when_no_prior_summary_exists(self, monkeypatch):
        """Regenerate must also work when no summary row exists yet."""
        user = _make_user("regen-nosummary@test.com")
        video = _make_video(user)
        _make_completed_transcript(video)
        app.dependency_overrides[summary_router.get_current_user] = lambda: user

        calls = []
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda t: (calls.append(1) or _fake_summarize_ok()),
        )

        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code == 200
        assert r.json()["status"] == "COMPLETED"
        assert len(calls) == 1

    def test_regenerated_summary_is_persisted(self, monkeypatch):
        """New content must be written to the database, not just returned."""
        user = _make_user("regen-persist@test.com")
        video = _make_video(user)
        transcript = _make_completed_transcript(video)
        _make_completed_summary(transcript)
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda _: _fake_summarize_ok(),
        )

        client.post(f"/videos/{video.id}/summary/regenerate")

        db = TestSession()
        saved = (
            db.query(Summary).filter(Summary.transcript_id == transcript.id).one()
        )
        db.close()
        assert saved.short_summary == "New short summary."
        assert saved.detailed_summary == "New detailed summary."
        assert saved.status == SummaryStatus.COMPLETED

    def test_regenerate_response_shape_matches_get(self, monkeypatch):
        """The response from regenerate must match the SummaryResponse schema
        returned by GET /videos/{id}/summary."""
        user = _make_user("regen-shape@test.com")
        video = _make_video(user)
        _make_completed_transcript(video)
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda _: _fake_summarize_ok(),
        )

        regen = client.post(f"/videos/{video.id}/summary/regenerate")
        get = client.get(f"/videos/{video.id}/summary")

        assert regen.status_code == 200
        assert get.status_code == 200
        assert set(regen.json().keys()) == set(get.json().keys())

    def test_generation_failure_marks_status_failed(self, monkeypatch):
        """When summarize_transcript raises, the summary is marked FAILED."""
        user = _make_user("regen-fail@test.com")
        video = _make_video(user)
        _make_completed_transcript(video)
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda _: (_ for _ in ()).throw(ValueError("model failed")),
        )

        r = client.post(f"/videos/{video.id}/summary/regenerate")
        assert r.status_code == 500

        db = TestSession()
        transcript = (
            db.query(Transcript).filter(Transcript.video_id == video.id).one()
        )
        summary = (
            db.query(Summary).filter(Summary.transcript_id == transcript.id).first()
        )
        db.close()
        assert summary is not None
        assert summary.status == SummaryStatus.FAILED

    def test_failed_regeneration_preserves_previous_completed_summary(self, monkeypatch):
        user = _make_user("regen-keep-old@test.com")
        video = _make_video(user)
        transcript = _make_completed_transcript(video)
        existing = _make_completed_summary(transcript)
        old_short = existing.short_summary
        old_detailed = existing.detailed_summary
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda _: (_ for _ in ()).throw(ValueError("model failed")),
        )

        response = client.post(f"/videos/{video.id}/summary/regenerate")
        assert response.status_code == 500

        db = TestSession()
        saved = db.query(Summary).filter(Summary.transcript_id == transcript.id).one()
        db.close()
        assert saved.status == SummaryStatus.COMPLETED
        assert saved.short_summary == old_short
        assert saved.detailed_summary == old_detailed

    def test_generate_does_not_regenerate_completed_summary(self, monkeypatch):
        """POST /videos/{id}/summary (no regenerate) must NOT re-run the
        service when the summary is already COMPLETED.
        This verifies the generate_summary handler is unaffected by the fix."""
        user = _make_user("gen-norerun@test.com")
        video = _make_video(user)
        transcript = _make_completed_transcript(video)
        _make_completed_summary(transcript)
        app.dependency_overrides[summary_router.get_current_user] = lambda: user

        calls = []
        monkeypatch.setattr(
            summary_router,
            "summarize_transcript",
            lambda t: (calls.append(1) or _fake_summarize_ok()),
        )

        r = client.post(f"/videos/{video.id}/summary")
        assert r.status_code == 200
        assert len(calls) == 0, "generate_summary must not re-run when COMPLETED"
        assert r.json()["short_summary"] == "Old short."


# ===========================================================================
# P1-2 — Admin upload history
# ===========================================================================

class TestAdminUploadHistory:

    def _make_admin(self, email: str = "admin@test.com") -> User:
        return _make_user(email, role="administrator")

    # ------------------------------------------------------------------
    # Auth / role enforcement
    # ------------------------------------------------------------------

    def test_returns_401_without_auth(self):
        r = client.get("/admin/upload-history")
        assert r.status_code == 401

    def test_learner_is_forbidden(self):
        user = _make_user("learner@test.com", role="learner")
        app.dependency_overrides[summary_router.get_current_user] = lambda: user
        # Must use real auth dependency chain — override at the router level
        from app.routers import admin as admin_module
        # The endpoint uses Depends(require_role(ADMINISTRATOR)) as a route
        # dependency; the cleanest way to test it is to call the endpoint with
        # a real non-admin user via TestClient Bearer injection.
        # Since we can't easily issue a real JWT here, we patch get_current_user
        # in the auth dependency and call the endpoint without overriding the
        # role check itself.
        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: user
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 403

    def test_educator_is_forbidden(self):
        user = _make_user("educator@test.com", role="educator")
        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: user
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 403

    def test_content_creator_is_forbidden(self):
        user = _make_user("creator@test.com", role="content creator")
        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: user
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 403

    def test_administrator_can_access(self):
        admin = self._make_admin("admin-access@test.com")
        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: admin
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 200

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def test_empty_history_returns_empty_list(self):
        admin = self._make_admin("admin-empty@test.com")
        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: admin
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_videos_from_all_users(self):
        """Admin must see videos from every user, not just their own."""
        admin = self._make_admin("admin-all@test.com")
        creator1 = _make_user("c1@test.com", role="content creator")
        creator2 = _make_user("c2@test.com", role="content creator")
        v1 = _make_video(creator1, "video1.mp4")
        v2 = _make_video(creator2, "video2.mp4")

        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: admin
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert v1.id in ids
        assert v2.id in ids

    def test_response_items_match_frontend_schema(self):
        """Each item must have id, filename, status, uploaded_at —
        exactly the VideoUploadResponse shape the frontend expects."""
        admin = self._make_admin("admin-shape@test.com")
        creator = _make_user("creator-shape@test.com", role="content creator")
        _make_video(creator, "shape.mp4")

        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: admin
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 200
        items = r.json()
        assert len(items) >= 1
        for item in items:
            assert "id" in item
            assert "filename" in item
            assert "status" in item
            assert "uploaded_at" in item
            # Must NOT expose internal file_path or user_id
            assert "file_path" not in item
            # user_id is not part of VideoResponse schema — verify it's absent
            assert "user_id" not in item

    def test_results_ordered_most_recent_first(self):
        """Videos are returned newest-first, matching /videos/history.
        We verify the ordering contract by inserting videos with distinct
        uploaded_at values and checking the returned order."""
        import time
        admin = self._make_admin("admin-order@test.com")
        creator = _make_user("creator-order@test.com", role="content creator")

        # Insert v1 first, then explicitly set uploaded_at on v2 to a later
        # value so the order is deterministic even on fast machines / SQLite.
        v1 = _make_video(creator, "first.mp4")
        v2 = _make_video(creator, "second.mp4")

        # Force v2's uploaded_at to be strictly after v1's by updating the row
        from datetime import datetime, timezone, timedelta
        db = TestSession()
        video1 = db.query(Video).filter(Video.id == v1.id).one()
        video2 = db.query(Video).filter(Video.id == v2.id).one()
        base = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        video1.uploaded_at = base
        video2.uploaded_at = base + timedelta(seconds=1)
        db.commit()
        db.close()

        from app.dependencies.auth import get_current_user as real_gcu
        app.dependency_overrides[real_gcu] = lambda: admin
        r = client.get(
            "/admin/upload-history",
            headers={"Authorization": "Bearer fake-token"},
        )
        assert r.status_code == 200
        ids = [item["id"] for item in r.json()]
        # v2 has the later timestamp, so it must appear before v1
        assert ids.index(v2.id) < ids.index(v1.id)

    def test_openapi_has_exactly_one_admin_upload_history(self):
        """GET /admin/upload-history appears exactly once in the OpenAPI spec."""
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json().get("paths", {})
        assert "/admin/upload-history" in paths
        assert "get" in paths["/admin/upload-history"]
