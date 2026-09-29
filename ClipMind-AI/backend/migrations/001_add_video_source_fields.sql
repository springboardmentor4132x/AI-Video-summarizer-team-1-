-- Add source metadata for uploaded and YouTube-backed videos.
ALTER TABLE videos
  ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'UPLOAD';

ALTER TABLE videos
  ADD COLUMN IF NOT EXISTS source_url TEXT;

UPDATE videos
SET source_type = 'UPLOAD'
WHERE source_type IS NULL;
