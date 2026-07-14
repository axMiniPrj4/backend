from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin


class TodoStatus:
    DONE = "DONE"
    NOT_DONE = "NOT_DONE"

    ALL = {DONE, NOT_DONE}


class Todo(Base, TimestampMixin, SoftDeleteMixin):
    """개인 전용 Todo — 프로젝트와 무관 (project_id 없음)."""

    __tablename__ = "todo"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    content: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=TodoStatus.NOT_DONE)
