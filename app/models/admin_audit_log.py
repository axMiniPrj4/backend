from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, TimestampMixin

_BigInt = BigInteger().with_variant(Integer(), "sqlite")


class AdminAuditLog(Base, TimestampMixin):
    """관리자 사이트 작업 감사 로그 (삭제·정지 등). SoftDelete 없음."""

    __tablename__ = "admin_audit_log"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    admin_login_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str] = mapped_column(String(30), nullable=False)
    target_id: Mapped[int | None] = mapped_column(_BigInt, nullable=True)
    target_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
