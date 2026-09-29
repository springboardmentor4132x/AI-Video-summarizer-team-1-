"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Runtime settings for the FastAPI application."""

    app_name: str = "ClipMind AI API"
    app_version: str = "0.1.0"
    debug: bool = False
    db_user: str
    db_password: str
    db_host: str
    db_port: int
    db_name: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    max_video_size_bytes: int = 524_288_000
    storage_backend: Literal["local", "s3"] = "s3"
    local_storage_path: str = "uploads"
    s3_bucket: str | None = None
    s3_region: str = "us-east-1"
    s3_prefix: str = "videos"
    s3_endpoint_url: str | None = None
    aws_access_key_id: SecretStr | None = None
    aws_secret_access_key: SecretStr | None = None
    aws_session_token: SecretStr | None = None
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    ffmpeg_timeout_seconds: int = 300
    youtube_socket_timeout_seconds: int = 30
    youtube_max_retries: int = 2
    youtube_fragment_retries: int = 2
    youtube_max_duration_seconds: int = 4 * 60 * 60
    whisper_model: str = "base"
    whisper_language: str | None = None
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> URL:
        """Build the PostgreSQL URL from environment-backed components."""

        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""

    return Settings()


settings = get_settings()
