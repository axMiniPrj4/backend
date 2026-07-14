"""task multi-assignee — task_assignee table, drop task.assignee_id

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


def _drop_assignee_fk() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "mysql":
        return
    rows = bind.execute(
        sa.text(
            "SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'task' "
            "AND COLUMN_NAME = 'assignee_id' AND REFERENCED_TABLE_NAME IS NOT NULL"
        )
    ).fetchall()
    for (name,) in rows:
        op.drop_constraint(name, "task", type_="foreignkey")


def upgrade() -> None:
    op.create_table(
        "task_assignee",
        sa.Column("task_id", _BigInt, nullable=False),
        sa.Column("user_id", _BigInt, nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("task_id", "user_id"),
    )
    op.execute("INSERT INTO task_assignee (task_id, user_id) SELECT id, assignee_id FROM task")
    _drop_assignee_fk()
    op.drop_column("task", "assignee_id")


def downgrade() -> None:
    op.add_column("task", sa.Column("assignee_id", _BigInt, nullable=True))
    op.execute(
        "UPDATE task SET assignee_id = ("
        "SELECT MIN(user_id) FROM task_assignee WHERE task_assignee.task_id = task.id)"
    )
    op.create_foreign_key("task_ibfk_assignee", "task", "user", ["assignee_id"], ["id"])
    op.drop_table("task_assignee")
