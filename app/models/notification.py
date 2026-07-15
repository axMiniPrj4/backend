from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class NotificationType:
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_COMMENT = "TASK_COMMENT"
    TASK_STATUS = "TASK_STATUS"

    ALL = {TASK_ASSIGNED, TASK_COMMENT, TASK_STATUS}


class Notification(Base, TimestampMixin):
    """개인 인앱 알림 — SoftDelete 없음 (읽음/미읽음만)."""

    __tablename__ = "notification"
    __table_args__ = (
        Index("ix_notification_user_created", "user_id", "created_at"),
        Index("ix_notification_user_unread", "user_id", "read_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("task.id"), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    actor: Mapped["User | None"] = relationship(foreign_keys=[actor_id])
