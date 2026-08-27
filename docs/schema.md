# Database Schema — ClipMind AI

This document describes the current database schema (Module 1) for the team.
Database: PostgreSQL, hosted on Supabase.

## Connection

The app connects using a single environment variable, loaded from `.env`
(never committed to Git — see `.env.example` for the expected format):

```
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres
```

## Tables

### users

Stores registered accounts and their role for access control.

| Column       | Type      | Constraints                        | Notes                                      |
|--------------|-----------|-------------------------------------|---------------------------------------------|
| id           | Integer   | Primary key, indexed                | Auto-incrementing                           |
| name         | String    | Not null                            | Display name                                |
| email        | String    | Unique, not null, indexed           | Used for login                              |
| password     | String    | Not null                            | Stored as a hash, never plain text          |
| role         | String    | Not null, default = 'learner'     | One of: content_creator, learner, educator, administrator |
| created_at   | DateTime  | Auto-set on insert (server default) | Timestamp with timezone                     |

### videos

Stores uploaded video metadata and processing status. Linked to the uploading user.

| Column       | Type      | Constraints                          | Notes                                     |
|--------------|-----------|----------------------------------------|--------------------------------------------|
| id           | Integer   | Primary key, indexed                   | Auto-incrementing                          |
| user_id      | Integer   | Foreign key -> users.id, not null      | The uploader                               |
| filename     | String    | Not null                               | Original filename                          |
| file_path    | String    | Not null                               | Storage location on disk/cloud             |
| status       | String    | Not null, default = 'uploaded'      | uploaded / processing / completed / failed |
| uploaded_at  | DateTime  | Auto-set on insert (server default)    | Timestamp with timezone                    |

## Relationship

One `user` can have many `videos` (one-to-many).
In code: `Video.owner` gives you the related `User`, and `User.videos`
(via backref) gives you all videos uploaded by that user.

## Migrations

Schema changes are managed with Alembic. Migration files live in
`backend/alembic/versions/`. To apply the latest schema to a fresh
database:

```bash
cd backend
alembic upgrade head
```

## Planned additions (future modules, not yet implemented)

- `transcripts` — speech-to-text output per video
- `summaries` — AI-generated short/detailed summaries per video
- `key_moments` — detected timestamps and importance scores per video
- `analytics_events` — usage tracking for the analytics dashboard

These are out of scope for Module 1 per the project plan.
