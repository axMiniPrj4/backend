from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, TimestampMixin


class PaymentKind:
    UPGRADE = "UPGRADE"  # FREE → PRO
    RENEW = "RENEW"  # PRO 재결제/기간 연장
    CANCEL = "CANCEL"  # 해지 (금액 0)


class PaymentStatus:
    PAID = "PAID"
    CANCELLED = "CANCELLED"  # 구독 해지 기록
    REFUNDED = "REFUNDED"


class PaymentMethod:
    CARD_MOCK = "CARD_MOCK"
    ADMIN = "ADMIN"


class Payment(Base, TimestampMixin):
    """유저 결제/요금제 변경 이력 — 관리자 결제내역 조회용."""

    __tablename__ = "payment"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    # 원화 정수 (예: Pro 월 33,000원). CANCEL은 0
    amount: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(10), nullable=False, default="KRW")
    plan: Mapped[str] = mapped_column(String(10), nullable=False)  # PRO / FREE
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=PaymentStatus.PAID)
    method: Mapped[str] = mapped_column(String(30), nullable=False, default=PaymentMethod.CARD_MOCK)
    order_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    payer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    payer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
