"""personal OPR per project, date, and author

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_opr_report_project_date", "opr_report", type_="unique")
    op.create_unique_constraint(
        "uq_opr_report_project_date_author",
        "opr_report",
        ["project_id", "report_date", "author_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_opr_report_project_date_author", "opr_report", type_="unique")
    op.create_unique_constraint(
        "uq_opr_report_project_date",
        "opr_report",
        ["project_id", "report_date"],
    )
