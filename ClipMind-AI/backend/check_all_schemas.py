from app.database import engine
from sqlalchemy import text

tables = ['key_moments', 'transcripts', 'upload_history']

for table_name in tables:
    print(f'\nColumns in {table_name} table:')
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{table_name}' ORDER BY ordinal_position"))
            for row in result:
                print(f'  {row[0]}: {row[1]}')
    except Exception as e:
        print(f'  Error: {e}')
