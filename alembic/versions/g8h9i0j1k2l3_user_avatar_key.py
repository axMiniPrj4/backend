"""user avatar_key column

Revision ID: g8h9i0j1k2l3
Revises: 1a2b3c4d5e6f
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "g8h9i0j1k2l3"
down_revision: Union[str, None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("avatar_key", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "avatar_key")
