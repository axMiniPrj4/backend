from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class TodoStatus:
    DONE = "DONE"
    NOT_DONE = "NOT_DONE"

    ALL = {DONE, NOT_DONE}


class TodoPriority:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    ALL = {LOW, MEDIUM, HIGH}


class Todo(Base, TimestampMixin, SoftDeleteMixin):
    """개인 전용 Todo — 프로젝트와 무관 (project_id 없음)."""

    __tablename__ = "todo"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    content: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoStatus.NOT_DONE)


class ProjectTodo(Base, TimestampMixin, SoftDeleteMixin):
    """프로젝트 할 일 — Task와 별개의 경량 체크리스트 (프론트 요구, 갭 분석 §3-1)."""

    __tablename__ = "project_todo"
    __table_args__ = (Index("ix_project_todo_project_deleted", "project_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)  # 작성자
    content: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoPriority.MEDIUM)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoStatus.NOT_DONE)

    author: Mapped["User"] = relationship()

    @property
    def author_nickname(self) -> str:
        return self.author.nickname
