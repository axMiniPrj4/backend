"""task wbs fields: category, work_group, color

Revision ID: b3c4d5e6f7a8
Revises: 6422a178c3d9
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "6422a178c3d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task",
        sa.Column("category", sa.String(length=50), nullable=False, server_default="기타"),
    )
    op.add_column(
        "task",
        sa.Column("work_group", sa.String(length=100), nullable=False, server_default=""),
    )
    op.add_column("task", sa.Column("color", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("task", "color")
    op.drop_column("task", "work_group")
    op.drop_column("task", "category")
