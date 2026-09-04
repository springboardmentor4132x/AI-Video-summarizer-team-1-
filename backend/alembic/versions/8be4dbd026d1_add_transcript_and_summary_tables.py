"""add transcript and summary tables

Revision ID: 8be4dbd026d1
Revises: 89b856a8da67
Create Date: 2026-09-04 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8be4dbd026d1"
down_revision: Union[str, Sequence[str], None] = "89b856a8da67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("language", sa.String(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("NOT_STARTED", "PROCESSING", "COMPLETED", "FAILED", name="transcriptstatus"),
            nullable=True,
        ),
        sa.Column("segments", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("video_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("video_id"),
    )
    op.create_index(op.f("ix_transcripts_id"), "transcripts", ["id"], unique=False)

    op.create_table(
        "summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_summary", sa.Text(), nullable=True),
        sa.Column("detailed_summary", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("NOT_STARTED", "PROCESSING", "COMPLETED", "FAILED", name="summarystatus"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("transcript_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transcript_id"),
    )
    op.create_index(op.f("ix_summaries_id"), "summaries", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_summaries_id"), table_name="summaries")
    op.drop_table("summaries")
    op.drop_index(op.f("ix_transcripts_id"), table_name="transcripts")
    op.drop_table("transcripts")