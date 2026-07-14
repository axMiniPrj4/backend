"""merge_signup_and_collaboration

Revision ID: 6422a178c3d9
Revises: a7b8c9d0e1f2, a8b9c0d1e2f3
Create Date: 2026-07-15 00:31:06.633535

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6422a178c3d9'
down_revision: Union[str, None] = ('a7b8c9d0e1f2', 'a8b9c0d1e2f3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
