from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, BigIntPK, SoftDeleteMixin, TimestampMixin, utcnow

_LongText = Text().with_variant(LONGTEXT(), "mysql")


class ChatMessage(Base):
    __tablename__ = "chat_message"
    __table_args__ = (Index("ix_chat_message_project_id", "project_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="text")  # text|emoji|image
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_data: Mapped[str | None] = mapped_column(_LongText, nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class WhiteboardBoard(Base):
    __tablename__ = "whiteboard_board"

    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    objects: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    size_key: Mapped[str] = mapped_column(String(30), nullable=False, default="square")
    custom_width: Mapped[int] = mapped_column(Integer, nullable=False, default=1280)
    custom_height: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    zoom: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class WorkspaceFile(Base):
    __tablename__ = "workspace_file"
    __table_args__ = (
        Index("ix_workspace_file_project_id", "project_id"),
        UniqueConstraint("project_id", "path", name="uq_workspace_file_project_path"),
    )

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False, default="plaintext")
    content: Mapped[str] = mapped_column(_LongText, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class WorkspaceFileVersion(Base):
    __tablename__ = "workspace_file_version"
    __table_args__ = (Index("ix_workspace_file_version_file_id", "file_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("workspace_file.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(_LongText, nullable=False)
    saved_by: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    saved_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ErdDocument(Base):
    __tablename__ = "erd_document"

    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    dbml: Mapped[str] = mapped_column(_LongText, nullable=False, default="")
    positions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    zoom: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    split_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=36)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class VideoSession(Base):
    __tablename__ = "video_session"

    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    joined: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    muted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    camera_off: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class AiThread(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "ai_thread"
    __table_args__ = (Index("ix_ai_thread_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="새 대화")


class AiMessage(Base):
    __tablename__ = "ai_message"
    __table_args__ = (Index("ix_ai_message_thread_id", "thread_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(ForeignKey("ai_thread.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user|assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_event"
    __table_args__ = (Index("ix_calendar_event_project_id", "project_id"),)

    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    event_time: Mapped[str | None] = mapped_column(String(10), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("user.id"), nullable=False)
