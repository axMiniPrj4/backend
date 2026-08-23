from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class TodoStatus:
    DONE = "DONE"
    NOT_DONE = "NOT_DONE"
    IN_PROGRESS = "IN_PROGRESS"

    ALL = {DONE, NOT_DONE, IN_PROGRESS}


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
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=TodoStatus.NOT_DONE)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoPriority.MEDIUM)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    color: Mapped[str | None] = mapped_column(String(20), nullable=True)


class ProjectTodo(Base, TimestampMixin, SoftDeleteMixin):
    """프로젝트 할 일 — Task와 별개의 경량 체크리스트 (프론트 요구, 갭 분석 §3-1).

    parent_id로 중첩 트리를 구성 (KnotQ의 스킴 참고, 2026-08-24) — 최상위 항목이 제목 역할,
    자식 항목이 하위 체크박스가 되는 구조.
    """

    __tablename__ = "project_todo"
    __table_args__ = (
        Index("ix_project_todo_project_deleted", "project_id", "deleted_at"),
        Index("ix_project_todo_parent", "parent_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)  # 작성자
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("project_todo.id"), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content: Mapped[str] = mapped_column(String(200), nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoPriority.MEDIUM)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoStatus.NOT_DONE)

    author: Mapped["User"] = relationship()
    children: Mapped[list["ProjectTodo"]] = relationship(
        back_populates="parent",
        order_by="ProjectTodo.sort_order, ProjectTodo.id",
    )
    parent: Mapped["ProjectTodo | None"] = relationship(back_populates="children", remote_side=[id])

    @property
    def author_nickname(self) -> str:
        return self.author.nickname
