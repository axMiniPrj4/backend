from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin


class UserRole:
    USER = "USER"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"


class UserPlan:
    FREE = "FREE"
    PRO = "PRO"


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "user"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    # 탈퇴 시 `del_{ts}_{원본}` 변형 저장을 고려해 길이 여유 확보
    login_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    nickname: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=UserRole.USER)
    plan: Mapped[str] = mapped_column(String(10), nullable=False, default=UserPlan.FREE)
    plan_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 가입 시 필수 동의 기록 (감사 목적 — 시드 등 예외 경로는 NULL 가능)
    terms_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    privacy_agreed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
