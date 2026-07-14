from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin


class NoticeCategory:
    SERVICE = "SERVICE"
    UPDATE = "UPDATE"

    ALL = {SERVICE, UPDATE}


class Notice(Base, TimestampMixin, SoftDeleteMixin):
    """공지사항 — 사용자 조회 전용, CRUD는 SYSTEM_ADMIN."""

    __tablename__ = "notice"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)  # 작성 관리자
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False, default=NoticeCategory.SERVICE)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
