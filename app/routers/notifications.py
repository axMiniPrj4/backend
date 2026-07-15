from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.errors import not_found
from app.db.base import utcnow
from app.db.session import get_db
from app.models import User
from app.models.notification import Notification
from app.schemas.notification import NotificationResponse, UnreadCountResponse

router = APIRouter(prefix="/api/notifications", tags=["Notification"])


def _to_response(row: Notification) -> NotificationResponse:
    data = NotificationResponse.model_validate(row)
    data.is_read = row.read_at is not None
    return data


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(30, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(Notification).where(Notification.user_id == user.id)
    if unread_only:
        stmt = stmt.where(Notification.read_at.is_(None))
    rows = db.scalars(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    ).all()
    return [_to_response(r) for r in rows]


@router.get("/unread-count", response_model=UnreadCountResponse)
def unread_count(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return UnreadCountResponse(count=int(count or 0))


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def mark_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
        )
    )
    if row is None:
        raise not_found("알림을 찾을 수 없습니다.")
    if row.read_at is None:
        row.read_at = utcnow()
        db.commit()
        db.refresh(row)
    return _to_response(row)


@router.post("/read-all", response_model=UnreadCountResponse)
def mark_all_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    now: datetime = utcnow()
    rows = db.scalars(
        select(Notification).where(
            Notification.user_id == user.id,
            Notification.read_at.is_(None),
        )
    ).all()
    for row in rows:
        row.read_at = now
    db.commit()
    return UnreadCountResponse(count=0)
