from datetime import datetime

from app.schemas.common import ORMModel


class PaymentResponse(ORMModel):
    id: int
    user_id: int
    amount: int
    currency: str
    plan: str
    kind: str
    status: str
    method: str
    order_id: str
    payer_name: str | None
    payer_email: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime


class AdminPaymentResponse(PaymentResponse):
    user_login_id: str = ""
    user_name: str = ""
    user_email: str = ""
