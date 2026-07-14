from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, utcnow


class LoginHistory(Base):
    """로그인 시도 기록 — append-only (수정·삭제 없음, TimestampMixin 미사용).

    존재하는 계정에 대한 시도만 적재한다 (미존재 아이디는 FK 대상이 없고,
    적재 시 아이디 존재 여부가 응답 시간으로 노출될 수 있어 제외).
    """

    __tablename__ = "login_history"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)  # IPv6 최대 45자
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
