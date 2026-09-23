"""Merge parallel migration branches

Revision ID: 762852703eb6
Revises: 61b0338b2c08, b64d5e92858b, b7f4c2d91e10
Create Date: 2026-09-10 19:59:46.720139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '762852703eb6'
down_revision: Union[str, Sequence[str], None] = ('61b0338b2c08', 'b64d5e92858b', 'b7f4c2d91e10')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
