# Database Design Documentation

Document the PostgreSQL schema and migration decisions here.

Module 1 entities:


Actual media files belong in cloud storage. PostgreSQL stores structured metadata and storage references.

# ClipMind AI Database Design

## Database

ClipMind AI uses PostgreSQL for durable structured data. The backend builds its connection from `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, and `DB_NAME`.

## Tables

### roles

Stores the unique role name assigned to users.

### users

Stores user ID, full name, normalized email, password hash, role foreign key, and creation timestamp. Passwords are never stored in plain text.

### videos

Stores:

- `id`
- `user_id` owner foreign key
- original filename
- private S3 `storage_key`
- MIME type
- byte size
- optional duration in seconds
- processing status
- upload, creation, and update timestamps

The binary video is not stored in this table.

### upload_history

Stores lifecycle events linked to a video:

- event ID
- video ID
- status
- precise event timestamp
- optional notes

Initial upload, processing start, completion, failure, and manual status transitions are recorded here.

## Relationships

```text
roles.id     1 --- many users.role_id
users.id     1 --- many videos.user_id
videos.id    1 --- many upload_history.video_id
```

Deleting a user cascades to their videos, and deleting a video cascades to its upload history. Cloud-object cleanup is handled by the storage service when a database write fails after an upload.

## Development and Production

Backend tests create an isolated SQLite schema from the SQLAlchemy models. The repository currently documents PostgreSQL setup but does not include an Alembic migration runner, so production schema migration automation remains future work. Do not treat test schema creation as a production migration strategy.
