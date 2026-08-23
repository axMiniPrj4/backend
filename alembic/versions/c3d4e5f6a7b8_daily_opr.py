"""daily project OPR reports and rows

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "opr_report",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="DRAFT"),
        sa.Column("author_id", _BigInt, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "report_date", name="uq_opr_report_project_date"),
    )
    op.create_index("ix_opr_report_project_date", "opr_report", ["project_id", "report_date"])
    op.create_table(
        "opr_row",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("report_id", _BigInt, nullable=False),
        sa.Column("section_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=True),
        sa.Column("assignee_name", sa.String(length=300), nullable=True),
        sa.Column("planned_date", sa.Date(), nullable=True),
        sa.Column("completed_date", sa.Date(), nullable=True),
        sa.Column("artifact_link", sa.String(length=1000), nullable=True),
        sa.Column("issue_request", sa.Text(), nullable=True),
        sa.Column("task_id", _BigInt, nullable=True),
        sa.Column("doc_id", _BigInt, nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="MANUAL"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["doc_id"], ["doc.id"]),
        sa.ForeignKeyConstraint(["report_id"], ["opr_report.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_opr_row_report_section", "opr_row", ["report_id", "section_type", "sort_order"])


def downgrade() -> None:
    op.drop_index("ix_opr_row_report_section", table_name="opr_row")
    op.drop_table("opr_row")
    op.drop_index("ix_opr_report_project_date", table_name="opr_report")
    op.drop_table("opr_report")
