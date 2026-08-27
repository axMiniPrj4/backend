"""task sort_order for WBS row ordering

Revision ID: i0j1k2l3m4n5
Revises: h9i0j1k2l3m4
Create Date: 2026-08-27

기존 데이터는 sort_order = id 로 백필한다. 현재 조회가 id 오름차순이므로
마이그레이션 후에도 화면 순서가 그대로 유지된다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "i0j1k2l3m4n5"
down_revision: Union[str, None] = "h9i0j1k2l3m4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "task",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    # 기존 행은 현재 표시 순서(id 오름차순)를 그대로 보존
    op.execute("UPDATE task SET sort_order = id")
    op.create_index("ix_task_project_sort", "task", ["project_id", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_task_project_sort", table_name="task")
    op.drop_column("task", "sort_order")
