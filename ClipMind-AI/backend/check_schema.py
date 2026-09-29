from app.database import engine
from sqlalchemy import text

with engine.connect() as conn:
    result = conn.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'summaries' ORDER BY ordinal_position"))
    print("Actual database columns in summaries table:")
    for row in result:
        print(f'  {row[0]}: {row[1]}')
