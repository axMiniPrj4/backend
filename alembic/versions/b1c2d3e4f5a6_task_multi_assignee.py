"""task 담당자 다중 선택 — task_assignee 연결 테이블 도입, task.assignee_id 제거

Revision ID: b1c2d3e4f5a6
Revises: 9829b4347e51
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "9829b4347e51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "task_assignee",
        sa.Column("task_id", _BigInt, nullable=False),
        sa.Column("user_id", _BigInt, nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("task_id", "user_id"),
    )
    # 기존 단일 담당자 데이터 이관
    op.execute("INSERT INTO task_assignee (task_id, user_id) SELECT id, assignee_id FROM task")
    # assignee_id 컬럼 제거 — FK가 걸려 있어 테이블 재생성 방식(batch) 사용
    with op.batch_alter_table("task", recreate="always") as batch:
        batch.drop_column("assignee_id")


def downgrade() -> None:
    with op.batch_alter_table("task", recreate="always") as batch:
        batch.add_column(sa.Column("assignee_id", _BigInt, nullable=True))
    # 다중 담당자 중 최소 user_id 1명만 보존
    op.execute(
        "UPDATE task SET assignee_id = ("
        "SELECT MIN(user_id) FROM task_assignee WHERE task_assignee.task_id = task.id)"
    )
    op.drop_table("task_assignee")
