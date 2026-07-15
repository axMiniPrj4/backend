"""project_member.collab_permission (EDITOR/VIEWER) 추가 — 공동작업 뷰어 권한

Revision ID: f7a8b9c0d1e2
Revises: e3f4a5b6c7d8
Create Date: 2026-07-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_member",
        sa.Column("collab_permission", sa.String(length=10), nullable=False, server_default="EDITOR"),
    )


def downgrade() -> None:
    op.drop_column("project_member", "collab_permission")
