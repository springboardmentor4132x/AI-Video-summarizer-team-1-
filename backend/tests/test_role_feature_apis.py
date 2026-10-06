from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base, get_db
from app.dependencies.auth import get_current_user
from app.main import app
from app.models.transcript import Transcript, TranscriptStatus
from app.models.user import User
from app.models.video import Video
from app.models.learning import Classroom, ClassroomMember, ClassroomResource, LearningHistory, SharedSummary


engine = create_engine(
    "sqlite:///./test_role_feature_apis.sqlite",
    connect_args={"check_same_thread": False},
)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
client = TestClient(app)


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    yield
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def make_user(email: str, role: str) -> User:
    db = Session()
    user = User(name=role.title(), email=email, password="hash", role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    db.expunge(user)
    db.close()
    return user


def authenticate(user: User) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


def make_video(user: User, filename: str, text: str) -> Video:
    db = Session()
    video = Video(
        user_id=user.id,
        filename=filename,
        file_path="/tmp/missing.mp4",
        status="completed",
        processing_stage="completed",
        processing_started_at=datetime.now(timezone.utc),
        processing_completed_at=datetime.now(timezone.utc),
    )
    db.add(video)
    db.flush()
    db.add(
        Transcript(
            video_id=video.id,
            text=text,
            language="en",
            segments=[
                {"start": 4.0, "end": 8.0, "text": text},
            ],
            status=TranscriptStatus.COMPLETED,
        )
    )
    db.commit()
    db.refresh(video)
    db.expunge(video)
    db.close()
    return video


def test_learner_can_search_only_owned_completed_transcripts():
    learner = make_user("learner-search@example.com", "learner")
    other = make_user("other-search@example.com", "content creator")
    lesson = make_video(learner, "lesson.mp4", "Python teaches machine learning concepts")
    db = Session()
    db.add(SharedSummary(educator_id=learner.id, video_id=lesson.id, audience="students"))
    db.commit()
    db.close()
    make_video(other, "private.mp4", "Python private material")
    authenticate(learner)

    response = client.get("/transcripts/search?q=machine")

    assert response.status_code == 200
    assert [item["filename"] for item in response.json()["results"]] == ["lesson.mp4"]
    assert response.json()["results"][0]["start_time"] == 4.0


def test_learner_browse_hides_unshared_completed_content():
    learner = make_user("learner-browse@example.com", "learner")
    owner = make_user("owner-browse@example.com", "educator")
    visible = make_video(owner, "shared.mp4", "Shared course material")
    make_video(owner, "private.mp4", "Private course material")
    db = Session()
    db.add(SharedSummary(educator_id=owner.id, video_id=visible.id, audience="students"))
    db.commit()
    db.close()
    authenticate(learner)

    response = client.get("/videos/")

    assert response.status_code == 200
    assert [item["filename"] for item in response.json()] == ["shared.mp4"]


def test_video_topics_return_transcript_backed_regions_and_respect_access():
    from app.models.learning import SharedSummary

    learner = make_user("learner-topic@example.com", "learner")
    educator = make_user("educator-topic@example.com", "educator")
    video = make_video(educator, "topic-lecture.mp4", "Neural networks learn useful patterns from training data.")
    authenticate(learner)

    assert client.get(f"/videos/{video.id}/topics").status_code == 404
    db = Session()
    db.add(SharedSummary(educator_id=educator.id, video_id=video.id, audience="students"))
    db.commit()
    db.close()
    response = client.get(f"/videos/{video.id}/topics")

    assert response.status_code == 200
    topic = response.json()["topics"][0]
    assert topic["start"] == 4.0
    assert topic["end"] == 8.0
    assert topic["segment_count"] == 1
    assert topic["text"] == "Neural networks learn useful patterns from training data."


def test_non_admin_cannot_use_admin_feature_apis():
    creator = make_user("creator-admin-api@example.com", "content creator")
    authenticate(creator)

    for path in ("/admin/users", "/admin/content", "/admin/processing", "/admin/storage"):
        assert client.get(path).status_code == 403


def test_admin_can_manage_users_and_monitor_processing_and_storage():
    admin = make_user("admin-feature-api@example.com", "administrator")
    creator = make_user("creator-feature-api@example.com", "content creator")
    video = make_video(creator, "lecture.mp4", "Architecture and deployment")
    authenticate(admin)

    users = client.get("/admin/users")
    assert users.status_code == 200
    assert any(item["id"] == creator.id for item in users.json())

    role_update = client.patch(
        f"/admin/users/{creator.id}/role",
        json={"role": "Educator"},
    )
    assert role_update.status_code == 200
    assert role_update.json()["role"] == "Educator"

    processing = client.get("/admin/processing")
    assert processing.status_code == 200
    assert processing.json()[0]["video_id"] == video.id
    assert processing.json()[0]["video_stage"] == "completed"

    storage = client.get("/admin/storage")
    assert storage.status_code == 200
    assert storage.json()["missing_video_files"] == 1


def test_admin_cannot_change_own_role():
    admin = make_user("admin-self-role@example.com", "administrator")
    authenticate(admin)

    response = client.patch(f"/admin/users/{admin.id}/role", json={"role": "Learner"})

    assert response.status_code == 403


def test_educator_material_crud_and_engagement_analytics_use_saved_history():
    educator = make_user("educator-workspace@example.com", "educator")
    learner = make_user("learner-workspace@example.com", "learner")
    video = make_video(educator, "lecture.mp4", "A lecture about systems")
    db = Session()
    db.add(SharedSummary(educator_id=educator.id, video_id=video.id, audience="students"))
    db.add(LearningHistory(user_id=learner.id, video_id=video.id, last_position_seconds=50, watch_duration_seconds=45, completion_percentage=50))
    db.commit()
    db.close()
    authenticate(educator)

    created = client.post("/educator/materials", json={"video_id": video.id, "title": "Study notes", "content": "Review the systems concepts."})
    assert created.status_code == 201
    material_id = created.json()["id"]
    updated = client.put(f"/educator/materials/{material_id}", json={"video_id": video.id, "title": "Updated notes", "content": "Review the updated concepts."})
    assert updated.status_code == 200
    assert updated.json()["title"] == "Updated notes"

    analytics = client.get("/educator/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["published_lectures"] == 1
    assert analytics.json()["unique_learners"] == 1
    assert analytics.json()["watch_time_seconds"] == 45
    assert analytics.json()["average_completion_percentage"] == 50

    creator_analytics = client.get("/analytics")
    assert creator_analytics.status_code == 200
    assert creator_analytics.json()["learner_engagement"]["learner_records"] == 1
    assert creator_analytics.json()["learner_engagement"]["unique_learners"] == 1
    assert creator_analytics.json()["learner_engagement"]["watch_time_seconds"] == 45

    assert client.delete(f"/educator/materials/{material_id}").status_code == 204


def test_classroom_analytics_excludes_nonmember_activity_for_shared_video():
    educator = make_user("educator-class-analytics@example.com", "educator")
    learner = make_user("member-class-analytics@example.com", "learner")
    outsider = make_user("outsider-class-analytics@example.com", "learner")
    video = make_video(educator, "shared-class.mp4", "Shared lesson")
    db = Session()
    room = Classroom(name="Scoped class", educator_id=educator.id, invite_code="scoped-class")
    db.add(room)
    db.flush()
    db.add(ClassroomMember(classroom_id=room.id, learner_id=learner.id))
    db.add(ClassroomResource(classroom_id=room.id, resource_type="video", resource_id=video.id, shared_by=educator.id))
    db.add_all([
        LearningHistory(user_id=learner.id, video_id=video.id, watch_duration_seconds=30, completion_percentage=60),
        LearningHistory(user_id=outsider.id, video_id=video.id, watch_duration_seconds=900, completion_percentage=100),
    ])
    db.commit()
    room_id = room.id
    db.close()
    authenticate(educator)

    response = client.get(f"/educator/classrooms/{room_id}/analytics")
    assert response.status_code == 200
    assert response.json()["learners"] == 1
    assert response.json()["views"] == 1
    assert response.json()["unique_viewers"] == 1
    assert response.json()["watch_time_seconds"] == 30
    assert response.json()["average_completion_percentage"] == 60


def test_classroom_invite_and_resource_access_are_membership_scoped():
    educator = make_user("educator-classroom@example.com", "educator")
    learner = make_user("learner-classroom@example.com", "learner")
    outsider = make_user("outsider-classroom@example.com", "learner")
    video = make_video(educator, "class-lecture.mp4", "Classroom lesson")

    authenticate(educator)
    created = client.post("/educator/classrooms", json={"name": "Biology 101", "description": "Cell systems"})
    assert created.status_code == 201
    classroom = created.json()
    shared = client.post(f"/educator/classrooms/{classroom['id']}/resources", json={"resource_type": "video", "resource_id": video.id})
    assert shared.status_code == 201

    authenticate(learner)
    joined = client.post("/learner/classrooms/join", json={"invite_code": classroom["invite_code"]})
    assert joined.status_code == 201
    resources = client.get(f"/learner/classrooms/{classroom['id']}/resources")
    assert resources.status_code == 200
    assert resources.json()[0]["resource"]["filename"] == "class-lecture.mp4"
    assert [item["filename"] for item in client.get("/videos/").json()] == ["class-lecture.mp4"]

    authenticate(outsider)
    assert client.get(f"/learner/classrooms/{classroom['id']}/resources").status_code == 404
