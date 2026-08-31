"""OPR AI 사용 기록.

하루 OPR(opr_report) 아래에 주제 단위로 여러 건을 남긴다.
AI 별로 쪼개지 않고 하나의 질문·답변 요약·적용 결과로 작성하며,
사용한 AI 는 opr_ai_record_provider 로 복수 연결한다.

연결 정책
- WBS(task)·자료(doc) 연결은 링크 테이블로 두고, 응답에는 id 목록만 내려준다.
  기존 opr_row.task_id/doc_id 와 같은 방식이라 프론트가 이미 가진 목록에서 제목을 찾는다.
- task/doc 은 소프트 삭제(deleted_at)를 쓰므로 실제로 행이 사라지는 일은 거의 없다.
  하드 삭제에 대비해 FK 는 ON DELETE CASCADE 로 두어 링크만 정리되게 한다.
  (기록 본문은 남는다 — OPR 이 삭제될 때만 함께 지워진다)
"""
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, TimestampMixin

if TYPE_CHECKING:
    from app.models.opr import OprReport
    from app.models.user import User


class AiProvider:
    CHATGPT = "CHATGPT"
    CLAUDE = "CLAUDE"
    GEMINI = "GEMINI"
    COPILOT = "COPILOT"
    PERPLEXITY = "PERPLEXITY"
    OTHER = "OTHER"

    ALL = {CHATGPT, CLAUDE, GEMINI, COPILOT, PERPLEXITY, OTHER}


class OprAiRecord(Base, TimestampMixin):
    __tablename__ = "opr_ai_record"
    __table_args__ = (Index("ix_opr_ai_record_report_sort", "report_id", "sort_order"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("opr_report.id", ondelete="CASCADE"), nullable=False
    )
    # 항상 report.author_id 와 같다. 조회 편의를 위해 복제해 두되 권한 판단의 기준은 report 다.
    author_id: Mapped[int] = mapped_column(BigIntPK, ForeignKey("user.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    application_result: Mapped[str] = mapped_column(Text, nullable=False)
    lesson_learned: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 결과물 URL. 길이는 opr_row.artifact_link 와 맞춘다.
    artifact_link: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    report: Mapped["OprReport"] = relationship(back_populates="ai_records")
    author: Mapped["User"] = relationship()
    providers: Mapped[list["OprAiRecordProvider"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="OprAiRecordProvider.provider",
    )
    task_links: Mapped[list["OprAiRecordTask"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="OprAiRecordTask.task_id",
    )
    doc_links: Mapped[list["OprAiRecordDoc"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="OprAiRecordDoc.doc_id",
    )

    @property
    def task_ids(self) -> list[int]:
        return [link.task_id for link in self.task_links]

    @property
    def doc_ids(self) -> list[int]:
        return [link.doc_id for link in self.doc_links]


class OprAiRecordProvider(Base):
    """기록 한 건에 사용한 AI. 같은 AI 중복은 복합 PK 로 막는다.

    custom_provider_name 을 PK 에 포함시킨 이유:
    '기타'를 서로 다른 이름으로 여러 개 넣을 수 있어야 하기 때문이다.
    MariaDB 는 NULL 값의 중복을 허용해 UNIQUE 가 걸리지 않으므로
    NULL 대신 NOT NULL DEFAULT '' 로 둔다.
    """

    __tablename__ = "opr_ai_record_provider"

    ai_record_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("opr_ai_record.id", ondelete="CASCADE"), primary_key=True
    )
    provider: Mapped[str] = mapped_column(String(30), primary_key=True)
    custom_provider_name: Mapped[str] = mapped_column(
        String(100), nullable=False, default="", server_default="", primary_key=True
    )

    record: Mapped["OprAiRecord"] = relationship(back_populates="providers")


class OprAiRecordTask(Base):
    """기록 ↔ WBS 작업 연결. 선택 사항이며 여러 건 연결할 수 있다."""

    __tablename__ = "opr_ai_record_task"
    __table_args__ = (Index("ix_opr_ai_record_task_task", "task_id"),)

    ai_record_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("opr_ai_record.id", ondelete="CASCADE"), primary_key=True
    )
    task_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("task.id", ondelete="CASCADE"), primary_key=True
    )

    record: Mapped["OprAiRecord"] = relationship(back_populates="task_links")


class OprAiRecordDoc(Base):
    """기록 ↔ 자료실 문서 연결.

    기존 자료를 가리키기만 한다 — 파일을 복사하거나 옮기지 않는다.
    """

    __tablename__ = "opr_ai_record_doc"
    __table_args__ = (Index("ix_opr_ai_record_doc_doc", "doc_id"),)

    ai_record_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("opr_ai_record.id", ondelete="CASCADE"), primary_key=True
    )
    doc_id: Mapped[int] = mapped_column(
        BigIntPK, ForeignKey("doc.id", ondelete="CASCADE"), primary_key=True
    )

    record: Mapped["OprAiRecord"] = relationship(back_populates="doc_links")
