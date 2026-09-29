-- Summary table migration for the existing SQLAlchemy Summary model.
-- This file is intentionally plain SQL because the project does not currently include Alembic.

CREATE TABLE IF NOT EXISTS summaries (
    id UUID PRIMARY KEY,
    video_id UUID NOT NULL UNIQUE,
    content TEXT NOT NULL DEFAULT '',
    overview TEXT NOT NULL DEFAULT '',
    main_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    key_takeaways JSONB NOT NULL DEFAULT '[]'::jsonb,
    duration_seconds INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED',
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_summaries_video
        FOREIGN KEY (video_id)
        REFERENCES videos (id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_summaries_video_id
    ON summaries (video_id);

ALTER TABLE summaries ADD COLUMN IF NOT EXISTS overview TEXT NOT NULL DEFAULT '';
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS main_points JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS key_takeaways JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS status VARCHAR(20) NOT NULL DEFAULT 'COMPLETED';
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS error_message TEXT;
