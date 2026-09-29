"""SQLAlchemy engine, session, and declarative model foundation."""

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base class inherited by all SQLAlchemy models."""


def ensure_database_compatibility() -> None:
    """Add legacy database columns expected by the ORM when older metadata already exists."""

    try:
        with engine.begin() as connection:
            if connection.dialect.name != "postgresql":
                return
            inspector = inspect(connection)
            if "summaries" not in inspector.get_table_names():
                return

            existing_columns = {column["name"] for column in inspector.get_columns("summaries")}
            upgrade_sql = [
                (
                    "overview",
                    'ALTER TABLE summaries ADD COLUMN IF NOT EXISTS overview TEXT NOT NULL DEFAULT ""',
                ),
                (
                    "main_points",
                    "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS main_points JSONB NOT NULL DEFAULT '[]'::jsonb",
                ),
                (
                    "key_takeaways",
                    "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS key_takeaways JSONB NOT NULL DEFAULT '[]'::jsonb",
                ),
                (
                    "duration_seconds",
                    "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS duration_seconds INTEGER",
                ),
                (
                    "status",
                    "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED'",
                ),
                (
                    "error_message",
                    "ALTER TABLE summaries ADD COLUMN IF NOT EXISTS error_message TEXT",
                ),
            ]
            for column_name, statement in upgrade_sql:
                if column_name not in existing_columns:
                    connection.execute(text(statement))

            if "key_moments" in inspector.get_table_names():
                key_moment_columns = {column["name"] for column in inspector.get_columns("key_moments")}
                if "topic" not in key_moment_columns:
                    connection.execute(text("ALTER TABLE key_moments ADD COLUMN IF NOT EXISTS topic VARCHAR(120)"))

            if "videos" in inspector.get_table_names():
                video_columns = {column["name"] for column in inspector.get_columns("videos")}
                if "source_type" not in video_columns:
                    connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'UPLOAD'"))
                if "source_url" not in video_columns:
                    connection.execute(text("ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_url TEXT"))
    except Exception:
        return


def create_database_engine() -> Engine:
    """Create the PostgreSQL engine from the configured environment URL."""

    return create_engine(settings.database_url, pool_pre_ping=True)


engine = create_database_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
ensure_database_compatibility()


def get_db() -> Generator[Session, None, None]:
    """Provide a database session for API dependencies."""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_database_connection() -> bool:
    """Verify that PostgreSQL accepts a simple query."""

    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
