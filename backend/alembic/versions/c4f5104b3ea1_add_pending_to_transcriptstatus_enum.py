"""add_pending_to_transcriptstatus_enum

Revision ID: c4f5104b3ea1
Revises: f9fc8b398117
Create Date: 2026-09-20 21:39:56.901629

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f5104b3ea1'
down_revision: Union[str, Sequence[str], None] = 'f9fc8b398117'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # PostgreSQL requires ALTER TYPE ... ADD VALUE to run outside a transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE transcriptstatus ADD VALUE IF NOT EXISTS 'PENDING'")



def downgrade() -> None:
    """Downgrade schema."""
    pass
