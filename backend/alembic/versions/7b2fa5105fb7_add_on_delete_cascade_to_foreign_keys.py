"""add_on_delete_cascade_to_foreign_keys

Revision ID: 7b2fa5105fb7
Revises: d2fabe9fbc9f
Create Date: 2026-10-02

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7b2fa5105fb7'
down_revision = 'd2fabe9fbc9f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to FKs and processing/error fields."""

    # ============================================================
    # 1. REPLACE FKs WITH ON DELETE CASCADE
    # ============================================================

    op.drop_constraint('videos_user_id_fkey', 'videos', type_='foreignkey')
    op.create_foreign_key(
        'videos_user_id_fkey', 'videos', 'users',
        ['user_id'], ['id'], ondelete='CASCADE'
    )

    op.drop_constraint('transcripts_video_id_fkey', 'transcripts', type_='foreignkey')
    op.create_foreign_key(
        'transcripts_video_id_fkey', 'transcripts', 'videos',
        ['video_id'], ['id'], ondelete='CASCADE'
    )

    op.drop_constraint('summaries_transcript_id_fkey', 'summaries', type_='foreignkey')
    op.create_foreign_key(
        'summaries_transcript_id_fkey', 'summaries', 'transcripts',
        ['transcript_id'], ['id'], ondelete='CASCADE'
    )

    op.drop_constraint('key_moments_video_id_fkey', 'key_moments', type_='foreignkey')
    op.create_foreign_key(
        'key_moments_video_id_fkey', 'key_moments', 'videos',
        ['video_id'], ['id'], ondelete='CASCADE'
    )

    # ============================================================
    # 2. ADD PROCESSING/ERROR FIELDS TO VIDEOS
    # ============================================================
    op.add_column('videos', sa.Column('processing_stage', sa.String(), nullable=True))
    op.add_column('videos', sa.Column('processing_error_code', sa.String(), nullable=True))
    op.add_column('videos', sa.Column('processing_error_message', sa.Text(), nullable=True))
    op.add_column('videos', sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('videos', sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('videos', sa.Column('duration_seconds', sa.Float(), nullable=True))

    # ============================================================
    # 3. ADD PROCESSING/ERROR FIELDS TO TRANSCRIPTS
    # ============================================================
    op.add_column('transcripts', sa.Column('error_code', sa.String(), nullable=True))
    op.add_column('transcripts', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('transcripts', sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('transcripts', sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('transcripts', sa.Column('processing_duration_seconds', sa.Float(), nullable=True))

    # ============================================================
    # 4. ADD PROCESSING/ERROR FIELDS TO SUMMARIES
    # ============================================================
    op.add_column('summaries', sa.Column('error_code', sa.String(), nullable=True))
    op.add_column('summaries', sa.Column('error_message', sa.Text(), nullable=True))
    op.add_column('summaries', sa.Column('processing_started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('summaries', sa.Column('processing_completed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('summaries', sa.Column('processing_duration_seconds', sa.Float(), nullable=True))


def downgrade() -> None:
    """Revert processing fields and cascade rules."""

    op.drop_column('summaries', 'processing_duration_seconds')
    op.drop_column('summaries', 'processing_completed_at')
    op.drop_column('summaries', 'processing_started_at')
    op.drop_column('summaries', 'error_message')
    op.drop_column('summaries', 'error_code')

    op.drop_column('transcripts', 'processing_duration_seconds')
    op.drop_column('transcripts', 'processing_completed_at')
    op.drop_column('transcripts', 'processing_started_at')
    op.drop_column('transcripts', 'error_message')
    op.drop_column('transcripts', 'error_code')

    op.drop_column('videos', 'duration_seconds')
    op.drop_column('videos', 'processing_completed_at')
    op.drop_column('videos', 'processing_started_at')
    op.drop_column('videos', 'processing_error_message')
    op.drop_column('videos', 'processing_error_code')
    op.drop_column('videos', 'processing_stage')

    op.drop_constraint('videos_user_id_fkey', 'videos', type_='foreignkey')
    op.create_foreign_key('videos_user_id_fkey', 'videos', 'users', ['user_id'], ['id'])

    op.drop_constraint('transcripts_video_id_fkey', 'transcripts', type_='foreignkey')
    op.create_foreign_key('transcripts_video_id_fkey', 'transcripts', 'videos', ['video_id'], ['id'])

    op.drop_constraint('summaries_transcript_id_fkey', 'summaries', type_='foreignkey')
    op.create_foreign_key('summaries_transcript_id_fkey', 'summaries', 'transcripts', ['transcript_id'], ['id'])

    op.drop_constraint('key_moments_video_id_fkey', 'key_moments', type_='foreignkey')
    op.create_foreign_key('key_moments_video_id_fkey', 'key_moments', 'videos', ['video_id'], ['id'])