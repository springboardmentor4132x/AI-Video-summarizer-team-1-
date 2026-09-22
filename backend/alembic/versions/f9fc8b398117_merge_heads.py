"""merge heads

Revision ID: f9fc8b398117
Revises: 61b0338b2c08, 89b856a8da67
Create Date: 2026-09-20 21:39:32.910986

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f9fc8b398117'
down_revision: Union[str, Sequence[str], None] = ('61b0338b2c08', '89b856a8da67')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
