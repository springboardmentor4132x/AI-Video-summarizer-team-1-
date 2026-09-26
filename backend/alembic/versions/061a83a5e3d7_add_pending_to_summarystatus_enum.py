"""add_pending_to_summarystatus_enum

Revision ID: 061a83a5e3d7
Revises: 652eb424d0f2
Create Date: 2026-09-25 18:45:09.979135

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '061a83a5e3d7'
down_revision = '652eb424d0f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL requires ALTER TYPE ... ADD VALUE to run outside a transaction
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE summarystatus ADD VALUE IF NOT EXISTS 'PENDING'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values safely — no-op
    pass