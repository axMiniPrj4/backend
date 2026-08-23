"""task and OPR document relations

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "task_doc_link",
        sa.Column("task_id", _BigInt, nullable=False),
        sa.Column("doc_id", _BigInt, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("linked_by", _BigInt, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["doc.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "doc_id"),
        sa.UniqueConstraint("task_id", "doc_id", name="uq_task_doc_link"),
    )
    op.create_index("ix_task_doc_project_task", "task_doc_link", ["project_id", "task_id"])
    op.create_index("ix_task_doc_project_doc", "task_doc_link", ["project_id", "doc_id"])

    op.create_table(
        "opr_report_doc_link",
        sa.Column("report_id", _BigInt, nullable=False),
        sa.Column("doc_id", _BigInt, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("linked_by", _BigInt, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["doc.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linked_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["opr_report.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("report_id", "doc_id"),
        sa.UniqueConstraint("report_id", "doc_id", name="uq_opr_report_doc_link"),
    )
    op.create_index("ix_opr_doc_project_report", "opr_report_doc_link", ["project_id", "report_id"])
    op.create_index("ix_opr_doc_project_doc", "opr_report_doc_link", ["project_id", "doc_id"])
    op.create_index("ix_opr_row_task_report", "opr_row", ["task_id", "report_id"])
    op.create_index("ix_opr_row_doc_report", "opr_row", ["doc_id", "report_id"])


def downgrade() -> None:
    op.drop_index("ix_opr_row_doc_report", table_name="opr_row")
    op.drop_index("ix_opr_row_task_report", table_name="opr_row")
    op.drop_index("ix_opr_doc_project_doc", table_name="opr_report_doc_link")
    op.drop_index("ix_opr_doc_project_report", table_name="opr_report_doc_link")
    op.drop_table("opr_report_doc_link")
    op.drop_index("ix_task_doc_project_doc", table_name="task_doc_link")
    op.drop_index("ix_task_doc_project_task", table_name="task_doc_link")
    op.drop_table("task_doc_link")
