from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.user import User


class Doc(Base, TimestampMixin, SoftDeleteMixin):
    """자료실 게시글 (title, content). 파일은 doc_version 이력으로 관리.

    project_id가 NULL이면 공통 자료 — 로그인 사용자 누구나 조회 가능 (2026-07-14 추가).
    """

    __tablename__ = "doc"

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("project.id"), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)  # 작성자
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    versions: Mapped[list["DocVersion"]] = relationship(back_populates="doc")
    author: Mapped["User"] = relationship()
    project: Mapped["Project | None"] = relationship()  # noqa: F821

    @property
    def latest_version(self) -> "DocVersion | None":
        alive = [v for v in self.versions if not v.is_deleted]
        return max(alive, key=lambda v: v.version_no) if alive else None

    @property
    def is_common(self) -> bool:
        return self.project_id is None


class DocVersion(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "doc_version"
    __table_args__ = (
        UniqueConstraint("doc_id", "version_no", name="uq_doc_version_no"),
        Index("ix_doc_version_doc_deleted", "doc_id", "deleted_at"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("doc.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    # 파일 메타 4종
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)  # 원본 파일명
    stored_name: Mapped[str] = mapped_column(String(255), nullable=False)  # UUID 저장명
    file_size: Mapped[int] = mapped_column(BigIntPK, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)

    doc: Mapped["Doc"] = relationship(back_populates="versions")
    uploader: Mapped["User"] = relationship()
