"""merge_login_history_and_wbs

Revision ID: 9840c2778d3b
Revises: b8c9d0e1f2a3, b3c4d5e6f7a8
Create Date: 2026-07-15 03:20:07.144201

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9840c2778d3b'
down_revision: Union[str, None] = ('b8c9d0e1f2a3', 'b3c4d5e6f7a8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
