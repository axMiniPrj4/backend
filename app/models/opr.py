from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, TimestampMixin

if TYPE_CHECKING:
    from app.models.doc import Doc
    from app.models.opr_ai import OprAiRecord
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
    ai_records: Mapped[list["OprAiRecord"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="OprAiRecord.sort_order, OprAiRecord.id",
    )

    @property
    def author_nickname(self) -> str:
        """OPR 작성자 표시명 — 실명 우선, 없으면 닉네임."""
        if not self.author:
            return ""
        return (self.author.name or self.author.nickname or "").strip()

    @property
    def author_name(self) -> str:
        return self.author_nickname


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
    doc_links: Mapped[list["OprRowDoc"]] = relationship(
        back_populates="row",
        cascade="all, delete-orphan",
        order_by="OprRowDoc.doc_id",
    )

    @property
    def doc_ids(self) -> list[int]:
        """이 행에 연결된 자료 id 목록. doc_id(대표)도 빠지지 않게 합친다."""
        ids = [link.doc_id for link in self.doc_links]
        if self.doc_id is not None and self.doc_id not in ids:
            ids.insert(0, self.doc_id)
        return ids


class OprRowDoc(Base):
    """OPR 행 ↔ 자료실 문서 (한 행에 여러 산출물).

    opr_row 는 저장할 때마다 지우고 다시 만들기 때문에 행 id 로 별도 관리하면
    저장 한 번에 연결이 날아간다. 그래서 행 데이터와 함께 재생성한다.
    """

    __tablename__ = "opr_row_doc"
    __table_args__ = (Index("ix_opr_row_doc_doc", "doc_id"),)

    row_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("opr_row.id", ondelete="CASCADE"), primary_key=True
    )
    doc_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("doc.id", ondelete="CASCADE"), primary_key=True
    )

    row: Mapped["OprRow"] = relationship(back_populates="doc_links")
