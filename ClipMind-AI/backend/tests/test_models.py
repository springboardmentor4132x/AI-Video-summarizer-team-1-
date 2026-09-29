from app.database import Base
from app.models import Role, UploadHistory, User, Video


def test_module_1_models_are_registered() -> None:
    assert {"roles", "users", "videos", "upload_history", "transcripts", "summaries", "key_moments"} == set(Base.metadata.tables)
    assert Role.__tablename__ == "roles"
    assert User.__tablename__ == "users"
    assert Video.__tablename__ == "videos"
    assert UploadHistory.__tablename__ == "upload_history"
