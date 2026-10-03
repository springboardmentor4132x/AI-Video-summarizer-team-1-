"""merge heads before cascade fix

Revision ID: d2fabe9fbc9f
Revises: 061a83a5e3d7, 8be4dbd026d1
Create Date: 2026-10-02 19:53:33.412548

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2fabe9fbc9f'
down_revision: Union[str, Sequence[str], None] = '061a83a5e3d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
