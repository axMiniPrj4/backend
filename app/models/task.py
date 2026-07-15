from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin, utcnow

if TYPE_CHECKING:
    from app.models.user import User


class TaskStatus:
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"

    ALL = {TODO, IN_PROGRESS, DONE}


class TaskPriority:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    ALL = {LOW, MEDIUM, HIGH}


# 담당자 다중 선택 — Hard Delete (재지정 시 행 교체)
task_assignee = Table(
    "task_assignee",
    Base.metadata,
    Column("task_id", BigIntPK, ForeignKey("task.id"), primary_key=True),
    Column("user_id", BigIntPK, ForeignKey("user.id"), primary_key=True),
)

# 댓글 좋아요 — Hard Delete (토글)
comment_like = Table(
    "comment_like",
    Base.metadata,
    Column("comment_id", BigIntPK, ForeignKey("task_comment.id"), primary_key=True),
    Column("user_id", BigIntPK, ForeignKey("user.id"), primary_key=True),
)


class Task(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "task"
    __table_args__ = (Index("ix_task_project_deleted", "project_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskStatus.TODO)
    creator_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="기타")
    work_group: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default=TaskPriority.MEDIUM)

    creator: Mapped["User"] = relationship(foreign_keys=[creator_id])
    assignees: Mapped[list["User"]] = relationship(secondary=task_assignee, order_by="User.id")

    @property
    def assignee_ids(self) -> list[int]:
        return [u.id for u in self.assignees]


class TaskHistory(Base):
    """Task 상태·담당 변경 타임라인."""

    __tablename__ = "task_history"
    __table_args__ = (Index("ix_task_history_task_created", "task_id", "created_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    actor: Mapped["User"] = relationship()

    @property
    def actor_nickname(self) -> str:
        return self.actor.nickname


class TaskComment(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "task_comment"
    __table_args__ = (Index("ix_task_comment_task_deleted", "task_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("task.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    content: Mapped[str] = mapped_column(String(1000), nullable=False)

    author: Mapped["User"] = relationship()
    likers: Mapped[list["User"]] = relationship(secondary=comment_like)

    @property
    def author_nickname(self) -> str:
        return self.author.nickname

    @property
    def like_count(self) -> int:
        return len(self.likers)
