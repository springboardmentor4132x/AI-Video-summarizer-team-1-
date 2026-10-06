"""add transcript summary and key moment tables

Revision ID: b7f4c2d91e10
Revises: 89b856a8da67
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b7f4c2d91e10"
down_revision: Union[str, Sequence[str], None] = "c4f5104b3ea1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Legacy duplicate table branch; the canonical parent already creates these tables."""
    pass


def downgrade() -> None:
    pass
