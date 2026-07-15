"""task.priority, personal todo fields, task_history

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.add_column(
        "task",
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="MEDIUM"),
    )

    op.add_column(
        "todo",
        sa.Column("priority", sa.String(length=10), nullable=False, server_default="MEDIUM"),
    )
    op.add_column("todo", sa.Column("description", sa.String(length=1000), nullable=True))
    op.add_column("todo", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("todo", sa.Column("end_date", sa.Date(), nullable=True))
    op.add_column("todo", sa.Column("color", sa.String(length=20), nullable=True))
    # status length: NOT_DONE / IN_PROGRESS / DONE
    op.alter_column(
        "todo",
        "status",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
    )

    op.create_table(
        "task_history",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("task_id", _BigInt, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("actor_id", _BigInt, nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_history_task_created", "task_history", ["task_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_task_history_task_created", table_name="task_history")
    op.drop_table("task_history")
    op.alter_column(
        "todo",
        "status",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
    op.drop_column("todo", "color")
    op.drop_column("todo", "end_date")
    op.drop_column("todo", "start_date")
    op.drop_column("todo", "description")
    op.drop_column("todo", "priority")
    op.drop_column("task", "priority")
