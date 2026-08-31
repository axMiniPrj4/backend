"""doc version attachment slot

Revision ID: m4n5o6p7q8r9
Revises: l3m4n5o6p7q8
Create Date: 2026-08-31

한 자료(doc)에 첨부를 여러 개 담기 위한 슬롯 도입.

- doc_version.slot 컬럼 추가 (NOT NULL DEFAULT 0) — 기존 행은 모두 0(대표 파일)이 되어
  동작이 달라지지 않는다.
- 유일 제약을 (doc_id, version_no) -> (doc_id, slot, version_no) 로 교체한다.
  슬롯마다 version_no 가 1부터 다시 시작하기 때문이다.

기존 데이터는 지우거나 바꾸지 않는다. 컬럼 추가와 제약 교체뿐이다.
MariaDB 의 DDL 은 트랜잭션이 아니므로 중간 실패 시 부분 적용될 수 있다.
그 경우 downgrade 로 되돌린 뒤 다시 실행하면 된다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "m4n5o6p7q8r9"
down_revision: Union[str, None] = "l3m4n5o6p7q8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doc_version",
        sa.Column("slot", sa.Integer(), nullable=False, server_default="0"),
    )
    # 기존 유일 제약을 슬롯 포함으로 교체
    op.drop_constraint("uq_doc_version_no", "doc_version", type_="unique")
    op.create_unique_constraint(
        "uq_doc_version_slot_no", "doc_version", ["doc_id", "slot", "version_no"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_doc_version_slot_no", "doc_version", type_="unique")
    op.create_unique_constraint("uq_doc_version_no", "doc_version", ["doc_id", "version_no"])
    op.drop_column("doc_version", "slot")
