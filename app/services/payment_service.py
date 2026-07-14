import secrets
from datetime import timedelta

from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.payment import Payment, PaymentKind, PaymentMethod, PaymentStatus
from app.models.user import User, UserPlan

PRO_MONTHLY_AMOUNT_KRW = 33000
PRO_DURATION_DAYS = 30


def _order_id() -> str:
    return f"ORD-{utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4).upper()}"


def record_payment(
    db: Session,
    *,
    user: User,
    kind: str,
    plan: str,
    amount: int,
    status: str,
    method: str = PaymentMethod.CARD_MOCK,
    payer_name: str | None = None,
    payer_email: str | None = None,
    note: str | None = None,
) -> Payment:
    payment = Payment(
        user_id=user.id,
        amount=amount,
        currency="KRW",
        plan=plan,
        kind=kind,
        status=status,
        method=method,
        order_id=_order_id(),
        payer_name=payer_name or user.name,
        payer_email=payer_email or user.email,
        note=note,
    )
    db.add(payment)
    return payment


def apply_plan_change(
    db: Session,
    user: User,
    *,
    next_plan: str,
    method: str = PaymentMethod.CARD_MOCK,
    payer_name: str | None = None,
    payer_email: str | None = None,
) -> Payment:
    """요금제 변경 + 결제 이력 기록. caller가 commit."""
    prev = user.plan
    if next_plan == UserPlan.PRO:
        kind = PaymentKind.RENEW if prev == UserPlan.PRO else PaymentKind.UPGRADE
        user.plan = UserPlan.PRO
        user.plan_expires_at = utcnow() + timedelta(days=PRO_DURATION_DAYS)
        return record_payment(
            db,
            user=user,
            kind=kind,
            plan=UserPlan.PRO,
            amount=PRO_MONTHLY_AMOUNT_KRW,
            status=PaymentStatus.PAID,
            method=method,
            payer_name=payer_name,
            payer_email=payer_email,
            note="Pro 월간 구독",
        )

    user.plan = UserPlan.FREE
    user.plan_expires_at = None
    return record_payment(
        db,
        user=user,
        kind=PaymentKind.CANCEL,
        plan=UserPlan.FREE,
        amount=0,
        status=PaymentStatus.CANCELLED,
        method=method,
        payer_name=payer_name,
        payer_email=payer_email,
        note="Pro 해지",
    )
