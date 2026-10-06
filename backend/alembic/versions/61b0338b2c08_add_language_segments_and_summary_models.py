"""Add language, segments, and summary models

Revision ID: 61b0338b2c08
Revises:
Create Date: 2026-09-08 18:22:46.334146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '61b0338b2c08'
down_revision: Union[str, Sequence[str], None] = 'b64d5e92858b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add transcript metadata and summaries after the transcript tables exist."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE transcriptstatus ADD VALUE IF NOT EXISTS 'PENDING'")
            op.execute("ALTER TYPE transcriptstatus ADD VALUE IF NOT EXISTS 'FAILED'")

    op.add_column('transcripts', sa.Column('language', sa.String(length=10), nullable=True))
    op.add_column('transcripts', sa.Column('segments', sa.JSON(), nullable=True))
    op.create_table('summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('short_summary', sa.Text(), nullable=True),
        sa.Column('detailed_summary', sa.Text(), nullable=True),
        sa.Column('status', sa.Enum('NOT_STARTED', 'PROCESSING', 'COMPLETED', 'FAILED', name='summarystatus'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('transcript_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['transcript_id'], ['transcripts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('transcript_id')
    )
    op.create_index(op.f('ix_summaries_id'), 'summaries', ['id'], unique=False)


def downgrade() -> None:
    """Remove summary and transcript metadata additions."""
    op.drop_column('transcripts', 'segments')
    op.drop_column('transcripts', 'language')
    op.drop_index(op.f('ix_summaries_id'), table_name='summaries')
    op.drop_table('summaries')
    if op.get_bind().dialect.name == "postgresql":
        op.execute('DROP TYPE summarystatus')
