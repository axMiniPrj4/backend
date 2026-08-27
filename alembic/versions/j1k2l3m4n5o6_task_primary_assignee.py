"""task primary assignee

Revision ID: j1k2l3m4n5o6
Revises: i0j1k2l3m4n5
Create Date: 2026-08-27

기존 데이터는 담당자 중 가장 작은 user_id를 주담당자로 백필한다.
프론트가 지금까지 assignees[0](= user.id 오름차순 첫 번째)을 대표처럼 표시해 왔으므로,
이렇게 채우면 화면 표시가 변하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, None] = "i0j1k2l3m4n5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("task", sa.Column("primary_assignee_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_task_primary_assignee", "task", "user", ["primary_assignee_id"], ["id"]
    )
    op.execute(
        """
        UPDATE task t
        SET primary_assignee_id = (
            SELECT MIN(ta.user_id) FROM task_assignee ta WHERE ta.task_id = t.id
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_task_primary_assignee", "task", type_="foreignkey")
    op.drop_column("task", "primary_assignee_id")
