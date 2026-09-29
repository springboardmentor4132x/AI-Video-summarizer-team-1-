from io import BytesIO

import pytest

from app.config import Settings
from app.services.storage import CloudStorageError, LocalStorage


def test_local_storage_round_trip_and_cleanup(tmp_path) -> None:
    storage = LocalStorage(
        Settings(
            db_user="user",
            db_password="password",
            db_host="localhost",
            db_port=5432,
            db_name="database",
            jwt_secret_key="secret",
            local_storage_path=str(tmp_path),
            storage_backend="local",
        )
    )
    storage_key = "videos/user-id/video-id.webm"
    source = BytesIO(b"video bytes")

    storage.upload_fileobj(source, storage_key, "video/webm")
    destination = BytesIO()
    storage.download_fileobj(storage_key, destination)

    assert destination.getvalue() == b"video bytes"
    assert (tmp_path / storage_key).is_file()

    storage.delete_object(storage_key)
    assert not (tmp_path / storage_key).exists()


def test_local_storage_rejects_path_traversal(tmp_path) -> None:
    storage = LocalStorage(
        Settings(
            db_user="user",
            db_password="password",
            db_host="localhost",
            db_port=5432,
            db_name="database",
            jwt_secret_key="secret",
            local_storage_path=str(tmp_path),
            storage_backend="local",
        )
    )

    with pytest.raises(CloudStorageError, match="Invalid local storage key"):
        storage.upload_fileobj(BytesIO(b"blocked"), "../outside.webm", "video/webm")