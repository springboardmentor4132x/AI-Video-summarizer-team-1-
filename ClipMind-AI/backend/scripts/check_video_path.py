#!/usr/bin/env python
"""Check video storage path."""

from app.database import SessionLocal
from app.models.video import Video
from sqlalchemy import select

db = SessionLocal()
video = db.execute(select(Video).where(Video.filename.contains("clipmind-library-valid"))).scalar_one_or_none()

if video:
    print(f"Video ID: {video.id}")
    print(f"Filename: {video.filename}")
    print(f"Storage Key: {video.storage_key}")
else:
    print("Video not found")

db.close()
