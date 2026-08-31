"""opr ai record

Revision ID: k2l3m4n5o6p7
Revises: j1k2l3m4n5o6
Create Date: 2026-08-31

OPR AI 사용 기록 — 신규 테이블 4개만 생성한다.
기존 테이블·컬럼·데이터는 일절 건드리지 않는다 (ALTER / DROP / UPDATE 없음).

MariaDB 의 DDL 은 트랜잭션이 아니라서 중간에 실패하면 일부 테이블만 남을 수 있다.
그 경우 생성된 테이블을 DROP 한 뒤 다시 실행하면 된다 — 신규 테이블뿐이라 데이터 손실은 없다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "k2l3m4n5o6p7"
down_revision: Union[str, None] = "j1k2l3m4n5o6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opr_ai_record",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.BigInteger(), nullable=False),
        sa.Column("author_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer_summary", sa.Text(), nullable=True),
        sa.Column("application_result", sa.Text(), nullable=False),
        sa.Column("lesson_learned", sa.Text(), nullable=True),
        sa.Column("artifact_link", sa.String(length=1000), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["opr_report.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opr_ai_record_report_sort", "opr_ai_record", ["report_id", "sort_order"]
    )

    # custom_provider_name 을 PK 에 포함해 '기타'를 서로 다른 이름으로 여러 개 넣을 수 있게 한다.
    # NULL 을 쓰면 MariaDB 가 중복을 허용해 유니크가 깨지므로 NOT NULL DEFAULT '' 로 둔다.
    op.create_table(
        "opr_ai_record_provider",
        sa.Column("ai_record_id", sa.BigInteger(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column(
            "custom_provider_name", sa.String(length=100), nullable=False, server_default=""
        ),
        sa.ForeignKeyConstraint(["ai_record_id"], ["opr_ai_record.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ai_record_id", "provider", "custom_provider_name"),
    )

    op.create_table(
        "opr_ai_record_task",
        sa.Column("ai_record_id", sa.BigInteger(), nullable=False),
        sa.Column("task_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["ai_record_id"], ["opr_ai_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["task.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ai_record_id", "task_id"),
    )
    op.create_index("ix_opr_ai_record_task_task", "opr_ai_record_task", ["task_id"])

    op.create_table(
        "opr_ai_record_doc",
        sa.Column("ai_record_id", sa.BigInteger(), nullable=False),
        sa.Column("doc_id", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["ai_record_id"], ["opr_ai_record.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_id"], ["doc.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("ai_record_id", "doc_id"),
    )
    op.create_index("ix_opr_ai_record_doc_doc", "opr_ai_record_doc", ["doc_id"])


def downgrade() -> None:
    # 신규 테이블만 제거한다. 기존 데이터에는 영향이 없다.
    op.drop_index("ix_opr_ai_record_doc_doc", table_name="opr_ai_record_doc")
    op.drop_table("opr_ai_record_doc")
    op.drop_index("ix_opr_ai_record_task_task", table_name="opr_ai_record_task")
    op.drop_table("opr_ai_record_task")
    op.drop_table("opr_ai_record_provider")
    op.drop_index("ix_opr_ai_record_report_sort", table_name="opr_ai_record")
    op.drop_table("opr_ai_record")
