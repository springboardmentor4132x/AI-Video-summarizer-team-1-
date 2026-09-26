"""merge Module 2 + Module 3 branches

Revision ID: 652eb424d0f2
Revises: b64d5e92858b, b7f4c2d91e10, c4f5104b3ea1
Create Date: 2026-09-25 18:39:19.408052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '652eb424d0f2'
down_revision: Union[str, Sequence[str], None] = ('b64d5e92858b', 'b7f4c2d91e10', 'c4f5104b3ea1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
