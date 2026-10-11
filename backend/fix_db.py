from app.db.session import engine
from sqlalchemy import text

with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE videos ADD COLUMN file_size_bytes INTEGER DEFAULT 0;"))
        conn.execute(text("ALTER TABLE videos ADD COLUMN duration_seconds INTEGER;"))
        print("Columns added successfully!")
    except Exception as e:
        print("Note: Columns might already exist or there was an error:", e)