"""Add persistent educator classrooms, membership and resources.

Revision ID: 6f2de87d64a1
Revises: e34895a1710c
"""
from alembic import op
import sqlalchemy as sa


revision = "6f2de87d64a1"
down_revision = "e34895a1710c"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "classrooms",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("educator_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invite_code", sa.String(40), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_classrooms_educator_id", "classrooms", ["educator_id"])
    op.create_index("ix_classrooms_invite_code", "classrooms", ["invite_code"], unique=True)
    op.create_table(
        "classroom_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learner_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("classroom_id", "learner_id", name="uq_classroom_member"),
    )
    op.create_index("ix_classroom_members_classroom_id", "classroom_members", ["classroom_id"])
    op.create_index("ix_classroom_members_learner_id", "classroom_members", ["learner_id"])
    op.create_table(
        "classroom_resources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("classroom_id", sa.Integer(), sa.ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_type", sa.String(20), nullable=False),
        sa.Column("resource_id", sa.Integer(), nullable=False),
        sa.Column("shared_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("classroom_id", "resource_type", "resource_id", name="uq_classroom_resource"),
    )
    op.create_index("ix_classroom_resources_classroom_id", "classroom_resources", ["classroom_id"])


def downgrade() -> None:
    op.drop_index("ix_classroom_resources_classroom_id", table_name="classroom_resources")
    op.drop_table("classroom_resources")
    op.drop_index("ix_classroom_members_learner_id", table_name="classroom_members")
    op.drop_index("ix_classroom_members_classroom_id", table_name="classroom_members")
    op.drop_table("classroom_members")
    op.drop_index("ix_classrooms_invite_code", table_name="classrooms")
    op.drop_index("ix_classrooms_educator_id", table_name="classrooms")
    op.drop_table("classrooms")
