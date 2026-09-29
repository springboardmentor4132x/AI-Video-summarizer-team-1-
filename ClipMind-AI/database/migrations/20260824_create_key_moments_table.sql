-- Key moments detected from existing timestamped transcripts.

CREATE TABLE IF NOT EXISTS key_moments (
    id UUID PRIMARY KEY,
    video_id UUID NOT NULL,
    start_time DOUBLE PRECISION NOT NULL,
    end_time DOUBLE PRECISION NOT NULL,
    title VARCHAR(100) NOT NULL,
    topic VARCHAR(120),
    description TEXT NOT NULL,
    importance_score DOUBLE PRECISION NOT NULL CHECK (importance_score >= 0 AND importance_score <= 1),
    transcript_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_key_moments_video
        FOREIGN KEY (video_id)
        REFERENCES videos (id)
        ON DELETE CASCADE,
    CONSTRAINT ck_key_moments_time_range CHECK (end_time > start_time)
);

CREATE INDEX IF NOT EXISTS ix_key_moments_video_id_start_time
    ON key_moments (video_id, start_time);

ALTER TABLE key_moments ADD COLUMN IF NOT EXISTS topic VARCHAR(120);
