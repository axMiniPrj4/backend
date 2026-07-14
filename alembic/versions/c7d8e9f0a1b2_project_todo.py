"""프로젝트 할 일(project_todo) 테이블 추가 — Task와 별개의 경량 체크리스트

Revision ID: c7d8e9f0a1b2
Revises: b1c2d3e4f5a6
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "project_todo",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("user_id", _BigInt, nullable=False),
        sa.Column("content", sa.String(length=200), nullable=False),
        sa.Column("priority", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_todo_project_deleted", "project_todo", ["project_id", "deleted_at"])


def downgrade() -> None:
    op.drop_index("ix_project_todo_project_deleted", table_name="project_todo")
    op.drop_table("project_todo")
