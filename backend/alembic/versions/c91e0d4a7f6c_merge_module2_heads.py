"""Merge the existing Module 1 and Module 2 migration heads.

Revision ID: c91e0d4a7f6c
Revises: 61b0338b2c08
"""

from typing import Sequence, Union


revision: str = "c91e0d4a7f6c"
down_revision: Union[str, Sequence[str], None] = "61b0338b2c08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
