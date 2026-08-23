from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, TimestampMixin

if TYPE_CHECKING:
    from app.models.doc import Doc
    from app.models.project import Project
    from app.models.task import Task
    from app.models.user import User


class OprSection:
    TODAY = "TODAY"
    COMPLETED = "COMPLETED"
    TOMORROW = "TOMORROW"
    ARTIFACT = "ARTIFACT"
    ISSUE = "ISSUE"

    ALL = {TODAY, COMPLETED, TOMORROW, ARTIFACT, ISSUE}


class OprReportStatus:
    DRAFT = "DRAFT"
    SHARED = "SHARED"
    CONFIRMED = "CONFIRMED"

    ALL = {DRAFT, SHARED, CONFIRMED}


class OprReport(Base, TimestampMixin):
    __tablename__ = "opr_report"
    __table_args__ = (
        UniqueConstraint("project_id", "report_date", "author_id", name="uq_opr_report_project_date_author"),
        Index("ix_opr_report_project_date", "project_id", "report_date"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id"), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=OprReportStatus.DRAFT)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    project: Mapped["Project"] = relationship()
    author: Mapped["User"] = relationship()
    rows: Mapped[list["OprRow"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="OprRow.sort_order, OprRow.id",
    )

    @property
    def author_nickname(self) -> str:
        return self.author.nickname


class OprRow(Base, TimestampMixin):
    __tablename__ = "opr_row"
    __table_args__ = (Index("ix_opr_row_report_section", "report_id", "section_type", "sort_order"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("opr_report.id", ondelete="CASCADE"), nullable=False)
    section_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    assignee_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    planned_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    completed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    artifact_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    issue_request: Mapped[str | None] = mapped_column(Text, nullable=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("task.id"), nullable=True)
    doc_id: Mapped[int | None] = mapped_column(ForeignKey("doc.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    report: Mapped["OprReport"] = relationship(back_populates="rows")
    task: Mapped["Task | None"] = relationship()
    doc: Mapped["Doc | None"] = relationship()
