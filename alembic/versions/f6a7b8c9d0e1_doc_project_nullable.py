"""공통 자료 지원 — doc.project_id NULL 허용 (NULL = 공통 자료)

Revision ID: f6a7b8c9d0e1
Revises: e4f5a6b7c8d9
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("doc") as batch:
        batch.alter_column("project_id", existing_type=_BigInt, nullable=True)


def downgrade() -> None:
    # 공통 자료(project_id NULL)가 있으면 NOT NULL 복원이 실패하므로 먼저 soft delete 처리
    op.execute("UPDATE doc SET deleted_at = CURRENT_TIMESTAMP WHERE project_id IS NULL AND deleted_at IS NULL")
    op.execute("DELETE FROM doc_version WHERE doc_id IN (SELECT id FROM doc WHERE project_id IS NULL)")
    op.execute("DELETE FROM doc WHERE project_id IS NULL")
    with op.batch_alter_table("doc") as batch:
        batch.alter_column("project_id", existing_type=_BigInt, nullable=False)
