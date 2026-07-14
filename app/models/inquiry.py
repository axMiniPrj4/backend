from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class InquiryStatus:
    WAITING = "WAITING"
    ANSWERED = "ANSWERED"

    ALL = {WAITING, ANSWERED}


class Inquiry(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "inquiry"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)  # 일반 문의는 NULL
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=InquiryStatus.WAITING)
    # 첨부 선택 1개 — 파일 메타 4종 (NULL 허용)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stored_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)

    answer: Mapped["Answer | None"] = relationship(back_populates="inquiry", uselist=False)
    author: Mapped["User"] = relationship()


class Answer(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("inquiry.id"), unique=True, nullable=False)  # 문의당 답변 1개
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)  # 답변한 ADMIN
    content: Mapped[str] = mapped_column(Text, nullable=False)

    inquiry: Mapped["Inquiry"] = relationship(back_populates="answer")
