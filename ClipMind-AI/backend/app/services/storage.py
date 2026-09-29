"""Local and cloud object storage integrations."""

import shutil
from pathlib import Path
from typing import BinaryIO

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings, settings


class CloudStorageError(Exception):
    """Raised when a cloud storage operation cannot be completed."""


class LocalStorage:
    """Store uploaded video objects under the backend's local upload directory."""

    def __init__(self, configuration: Settings = settings) -> None:
        storage_path = Path(configuration.local_storage_path)
        if not storage_path.is_absolute():
            storage_path = Path(__file__).resolve().parents[2] / storage_path
        self._root = storage_path.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, storage_key: str) -> Path:
        path = (self._root / storage_key).resolve()
        if path != self._root and self._root not in path.parents:
            raise CloudStorageError("Invalid local storage key")
        return path

    def upload_fileobj(self, fileobj: BinaryIO, storage_key: str, mime_type: str) -> None:
        """Save an upload under its generated storage key."""

        destination = self._resolve_key(storage_key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("wb") as output:
                shutil.copyfileobj(fileobj, output)
        except OSError as exc:
            raise CloudStorageError(f"Local video storage failed: {exc}") from exc

    def delete_object(self, storage_key: str) -> None:
        """Remove a local object when database persistence fails after upload."""

        try:
            self._resolve_key(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            raise CloudStorageError(f"Local video cleanup failed: {exc}") from exc

    def download_fileobj(self, storage_key: str, fileobj: BinaryIO) -> None:
        """Copy a local object into a caller-owned temporary file."""

        try:
            with self._resolve_key(storage_key).open("rb") as source:
                shutil.copyfileobj(source, fileobj)
        except OSError as exc:
            raise CloudStorageError(f"Local video read failed: {exc}") from exc


class S3Storage:
    """Store private video objects in Amazon S3."""

    def __init__(self, configuration: Settings = settings) -> None:
        if not configuration.s3_bucket:
            raise CloudStorageError("Cloud storage is not configured")

        client_options: dict[str, str] = {"region_name": configuration.s3_region}
        if configuration.s3_endpoint_url:
            client_options["endpoint_url"] = configuration.s3_endpoint_url
        if configuration.aws_access_key_id and configuration.aws_secret_access_key:
            client_options["aws_access_key_id"] = configuration.aws_access_key_id.get_secret_value()
            client_options["aws_secret_access_key"] = configuration.aws_secret_access_key.get_secret_value()
        if configuration.aws_session_token:
            client_options["aws_session_token"] = configuration.aws_session_token.get_secret_value()

        self._bucket = configuration.s3_bucket
        self._client = boto3.client("s3", **client_options)

    def upload_fileobj(self, fileobj: BinaryIO, storage_key: str, mime_type: str) -> None:
        """Upload a private object without returning credentials or a public URL."""

        try:
            self._client.upload_fileobj(
                fileobj,
                self._bucket,
                storage_key,
                ExtraArgs={
                    "ContentType": mime_type,
                    "ServerSideEncryption": "AES256",
                },
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            code = error.get("Code", "UnknownError")
            message = error.get("Message", str(exc))
            raise CloudStorageError(f"Cloud storage upload failed ({code}): {message}") from exc
        except BotoCoreError as exc:
            raise CloudStorageError(f"Cloud storage upload failed: {exc}") from exc

    def delete_object(self, storage_key: str) -> None:
        """Remove an object when database persistence fails after upload."""

        try:
            self._client.delete_object(Bucket=self._bucket, Key=storage_key)
        except (BotoCoreError, ClientError) as exc:
            raise CloudStorageError("Cloud storage cleanup failed") from exc

    def download_fileobj(self, storage_key: str, fileobj: BinaryIO) -> None:
        """Download a private object into a caller-owned temporary file."""

        try:
            self._client.download_fileobj(self._bucket, storage_key, fileobj)
        except (BotoCoreError, ClientError) as exc:
            raise CloudStorageError("Cloud storage download failed") from exc


def get_storage() -> LocalStorage | S3Storage:
    """Build the configured storage service for a request."""

    if settings.storage_backend == "local":
        return LocalStorage()
    return S3Storage()
