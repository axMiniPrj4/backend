"""project todo nesting: parent_id, sort_order

Revision ID: 1a2b3c4d5e6f
Revises: e5f6a7b8c9d0
Create Date: 2026-08-24

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "project_todo",
        sa.Column("parent_id", sa.BigInteger(), sa.ForeignKey("project_todo.id"), nullable=True),
    )
    op.add_column(
        "project_todo",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_project_todo_parent", "project_todo", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_project_todo_parent", table_name="project_todo")
    op.drop_column("project_todo", "sort_order")
    op.drop_column("project_todo", "parent_id")


revision: str = "1a2b3c4d5e6f"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
