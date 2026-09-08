"""Add language, segments, and summary models

Revision ID: 61b0338b2c08
Revises: 
Create Date: 2026-09-08 18:22:46.334146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '61b0338b2c08'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ============================================================
    # 1. CREATE SUMMARIES TABLE
    # ============================================================
    op.create_table('summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('short_summary', sa.Text(), nullable=True),
        sa.Column('detailed_summary', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', name='summarystatus'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('transcript_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transcript_id')
    )
    op.create_index(op.f('ix_summaries_id'), 'summaries', ['id'], unique=False)

    # ============================================================
    # 2. ADD COLUMNS TO TRANSCRIPTS
    # ============================================================
    op.add_column('transcripts', sa.Column('language', sa.String(length=10), nullable=True))
    op.add_column('transcripts', sa.Column('segments', sa.JSON(), nullable=True))

    # ============================================================
    # 3. CREATE KEY MOMENTS TABLE (IF NOT EXISTS)
    #    This is SAFE - it won't delete existing data
    # ============================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS key_moments (
            id SERIAL PRIMARY KEY,
            video_id INTEGER NOT NULL REFERENCES videos(id),
            start_time DOUBLE PRECISION NOT NULL,
            end_time DOUBLE PRECISION NOT NULL,
            title VARCHAR NOT NULL,
            topic VARCHAR,
            importance_score DOUBLE PRECISION NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
            highlight_path VARCHAR
        )
    """)
    
    # Create indexes if they don't exist
    op.execute("CREATE INDEX IF NOT EXISTS ix_key_moments_id ON key_moments (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_key_moments_video_id ON key_moments (video_id)")

    # ============================================================
    # 4. ADD PENDING/FAILED TO TRANSCRIPT STATUS ENUM (IF NOT EXISTS)
    # ============================================================
    op.execute("ALTER TYPE transcriptstatus ADD VALUE IF NOT EXISTS 'PENDING'")
    op.execute("ALTER TYPE transcriptstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    """Downgrade schema."""
    # ============================================================
    # 1. REMOVE COLUMNS FROM TRANSCRIPTS
    # ============================================================
    op.drop_column('transcripts', 'segments')
    op.drop_column('transcripts', 'language')

    # ============================================================
    # 2. DROP SUMMARIES TABLE
    # ============================================================
    op.drop_index(op.f('ix_summaries_id'), table_name='summaries')
    op.drop_table('summaries')

    # ============================================================
    # 3. DROP STATUS ENUMS
    # ============================================================
    op.execute('DROP TYPE summarystatus')

    # ============================================================
    # 4. DROP KEY MOMENTS TABLE (ONLY ON DOWNGRADE)
    # ============================================================
    op.drop_index('ix_key_moments_video_id', table_name='key_moments')
    op.drop_index('ix_key_moments_id', table_name='key_moments')
    op.drop_table('key_moments')