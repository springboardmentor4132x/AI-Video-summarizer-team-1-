"""add transcript summary and key moment tables

Revision ID: b7f4c2d91e10
Revises: 89b856a8da67
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f4c2d91e10"
down_revision: Union[str, Sequence[str], None] = "89b856a8da67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    transcript_status = sa.Enum(
        "PENDING", "NOT_STARTED", "PROCESSING", "COMPLETED", "FAILED",
        name="transcriptstatus",
    )
    summary_status = sa.Enum(
        "NOT_STARTED", "PROCESSING", "COMPLETED", "FAILED",
        name="summarystatus",
    )
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("segments", sa.JSON(), nullable=True),
        sa.Column("status", transcript_status, nullable=False, server_default="NOT_STARTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=False, unique=True),
    )
    op.create_index("ix_transcripts_id", "transcripts", ["id"])
    op.create_table(
        "summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("short_summary", sa.Text(), nullable=True),
        sa.Column("detailed_summary", sa.Text(), nullable=True),
        sa.Column("status", summary_status, nullable=False, server_default="NOT_STARTED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("transcript_id", sa.Integer(), sa.ForeignKey("transcripts.id"), nullable=False, unique=True),
    )
    op.create_index("ix_summaries_id", "summaries", ["id"])
    op.create_table(
        "key_moments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("video_id", sa.Integer(), sa.ForeignKey("videos.id"), nullable=False),
        sa.Column("start_time", sa.Float(), nullable=False),
        sa.Column("end_time", sa.Float(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("topic", sa.String(), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("highlight_path", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_key_moments_id", "key_moments", ["id"])
    op.create_index("ix_key_moments_video_id", "key_moments", ["video_id"])


def downgrade() -> None:
    op.drop_index("ix_key_moments_video_id", table_name="key_moments")
    op.drop_index("ix_key_moments_id", table_name="key_moments")
    op.drop_table("key_moments")
    op.drop_index("ix_summaries_id", table_name="summaries")
    op.drop_table("summaries")
    op.drop_index("ix_transcripts_id", table_name="transcripts")
    op.drop_table("transcripts")
    sa.Enum(name="summarystatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="transcriptstatus").drop(op.get_bind(), checkfirst=True)