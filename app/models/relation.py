from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, utcnow


class TaskDocLink(Base):
    __tablename__ = "task_doc_link"
    __table_args__ = (
        UniqueConstraint("task_id", "doc_id", name="uq_task_doc_link"),
        Index("ix_task_doc_project_task", "project_id", "task_id"),
        Index("ix_task_doc_project_doc", "project_id", "doc_id"),
    )

    task_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("task.id", ondelete="CASCADE"), primary_key=True)
    doc_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("doc.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    linked_by: Mapped[int] = mapped_column(BigIntPK, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class OprReportDocLink(Base):
    __tablename__ = "opr_report_doc_link"
    __table_args__ = (
        UniqueConstraint("report_id", "doc_id", name="uq_opr_report_doc_link"),
        Index("ix_opr_doc_project_report", "project_id", "report_id"),
        Index("ix_opr_doc_project_doc", "project_id", "doc_id"),
    )

    report_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("opr_report.id", ondelete="CASCADE"), primary_key=True)
    doc_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("doc.id", ondelete="CASCADE"), primary_key=True)
    project_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    linked_by: Mapped[int] = mapped_column(BigIntPK, ForeignKey("user.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
