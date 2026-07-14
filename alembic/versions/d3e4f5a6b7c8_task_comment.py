"""Task 댓글(task_comment) + 좋아요(comment_like) 테이블 추가

Revision ID: d3e4f5a6b7c8
Revises: c7d8e9f0a1b2
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "task_comment",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("task_id", _BigInt, nullable=False),
        sa.Column("user_id", _BigInt, nullable=False),
        sa.Column("content", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_comment_task_deleted", "task_comment", ["task_id", "deleted_at"])
    op.create_table(
        "comment_like",
        sa.Column("comment_id", _BigInt, nullable=False),
        sa.Column("user_id", _BigInt, nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["task_comment.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("comment_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("comment_like")
    op.drop_index("ix_task_comment_task_deleted", table_name="task_comment")
    op.drop_table("task_comment")
