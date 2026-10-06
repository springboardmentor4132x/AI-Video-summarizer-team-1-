"""Persist learner watch duration and completion.

Revision ID: e34895a1710c
Revises: 9c1f4a2e8b77
"""
from alembic import op
import sqlalchemy as sa


revision = "e34895a1710c"
down_revision = "9c1f4a2e8b77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("learning_history", sa.Column("watch_duration_seconds", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("learning_history", sa.Column("completion_percentage", sa.Float(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("learning_history", "completion_percentage")
    op.drop_column("learning_history", "watch_duration_seconds")
