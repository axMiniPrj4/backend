"""opr row doc link

Revision ID: l3m4n5o6p7q8
Revises: k2l3m4n5o6p7
Create Date: 2026-08-31

OPR 행 하나에 자료를 여러 개 연결하기 위한 링크 테이블.
신규 테이블 1개만 만들며 기존 테이블·컬럼·데이터는 건드리지 않는다.
기존 opr_row.doc_id 는 대표 산출물로 그대로 유지한다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "l3m4n5o6p7q8"
down_revision: Union[str, None] = "k2l3m4n5o6p7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opr_row_doc",
        sa.Column("row_id", sa.BigInteger(), nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["row_id"], ["opr_row.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_id"], ["doc.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("row_id", "doc_id"),
    )
    op.create_index("ix_opr_row_doc_doc", "opr_row_doc", ["doc_id"])


def downgrade() -> None:
    op.drop_index("ix_opr_row_doc_doc", table_name="opr_row_doc")
    op.drop_table("opr_row_doc")
