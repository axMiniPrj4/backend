"""가입 필수 동의 기록 — user.terms_agreed_at / privacy_agreed_at 추가

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("terms_agreed_at", sa.DateTime(), nullable=True))
    op.add_column("user", sa.Column("privacy_agreed_at", sa.DateTime(), nullable=True))
    # 기존 가입자는 가입 시각으로 소급 기록 (동의 UI 도입 전 가입자)
    op.execute("UPDATE user SET terms_agreed_at = created_at, privacy_agreed_at = created_at")


def downgrade() -> None:
    op.drop_column("user", "privacy_agreed_at")
    op.drop_column("user", "terms_agreed_at")
