from app.database import engine
from sqlalchemy import text

migration_sql = """
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS overview TEXT NOT NULL DEFAULT '';
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS main_points JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS key_takeaways JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS duration_seconds INTEGER;
ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_type VARCHAR(20) NOT NULL DEFAULT 'UPLOAD';
ALTER TABLE videos ADD COLUMN IF NOT EXISTS source_url TEXT;
"""

print("Running migration...")
with engine.connect() as conn:
    for statement in migration_sql.strip().split(';'):
        statement = statement.strip()
        if statement:
            print(f'Executing: {statement}')
            conn.execute(text(statement))
            conn.commit()
            print('  ✓ Success')

print('\nVerifying columns after migration:')
with engine.connect() as conn:
    result = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'summaries' ORDER BY ordinal_position"))
    for row in result:
        print(f'  {row[0]}: {row[1]}')
