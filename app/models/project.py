from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin, utcnow

if TYPE_CHECKING:
    from app.models.user import User


# 기준안: schema.sql 미제공으로 코드값 임의 확정 — 팀 승인 대상 (README 참고)
class ProjectStatus:
    PLANNED = "PLANNED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"

    ALL = {PLANNED, IN_PROGRESS, COMPLETED}


class ProjectPriority:
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    ALL = {LOW, MEDIUM, HIGH}


class MemberRole:
    LEADER = "LEADER"
    MEMBER = "MEMBER"


class Project(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "project"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default=ProjectPriority.MEDIUM)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ProjectStatus.PLANNED)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    members: Mapped[list["ProjectMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectMember(Base):
    """프로젝트 멤버 — Hard Delete 대상 (SoftDeleteMixin 미적용)."""

    __tablename__ = "project_member"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_member"),
        Index("ix_project_member_project_user", "project_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(10), nullable=False, default=MemberRole.MEMBER)
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    project: Mapped["Project"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship()
