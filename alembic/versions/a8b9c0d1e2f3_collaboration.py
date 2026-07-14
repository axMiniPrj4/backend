"""collaboration and mock-feature tables

Revision ID: a8b9c0d1e2f3
Revises: f6a7b8c9d0e1
Create Date: 2026-07-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_BigInt = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
_LongText = sa.Text().with_variant(mysql.LONGTEXT(), "mysql")


def upgrade() -> None:
    op.create_table(
        "chat_message",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("author_id", _BigInt, nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("image_data", _LongText, nullable=True),
        sa.Column("file_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_message_project_id", "chat_message", ["project_id"])

    op.create_table(
        "whiteboard_board",
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("objects", sa.JSON(), nullable=False),
        sa.Column("size_key", sa.String(length=30), nullable=False),
        sa.Column("custom_width", sa.Integer(), nullable=False),
        sa.Column("custom_height", sa.Integer(), nullable=False),
        sa.Column("zoom", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "workspace_file",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("path", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=False),
        sa.Column("content", _LongText, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", _BigInt, nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["updated_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "path", name="uq_workspace_file_project_path"),
    )
    op.create_index("ix_workspace_file_project_id", "workspace_file", ["project_id"])

    op.create_table(
        "workspace_file_version",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("file_id", _BigInt, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", _LongText, nullable=False),
        sa.Column("saved_by", _BigInt, nullable=False),
        sa.Column("saved_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["workspace_file.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["saved_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspace_file_version_file_id", "workspace_file_version", ["file_id"])

    op.create_table(
        "erd_document",
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("dbml", _LongText, nullable=False),
        sa.Column("positions", sa.JSON(), nullable=False),
        sa.Column("zoom", sa.Float(), nullable=False),
        sa.Column("split_percent", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "video_session",
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("joined", sa.Boolean(), nullable=False),
        sa.Column("muted", sa.Boolean(), nullable=False),
        sa.Column("camera_off", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("project_id"),
    )

    op.create_table(
        "ai_thread",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("user_id", _BigInt, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_thread_user_id", "ai_thread", ["user_id"])

    op.create_table(
        "ai_message",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("thread_id", _BigInt, nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["ai_thread.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_message_thread_id", "ai_message", ["thread_id"])

    op.create_table(
        "calendar_event",
        sa.Column("id", _BigInt, autoincrement=True, nullable=False),
        sa.Column("project_id", _BigInt, nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("event_time", sa.String(length=10), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", _BigInt, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["project.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_calendar_event_project_id", "calendar_event", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_calendar_event_project_id", table_name="calendar_event")
    op.drop_table("calendar_event")
    op.drop_index("ix_ai_message_thread_id", table_name="ai_message")
    op.drop_table("ai_message")
    op.drop_index("ix_ai_thread_user_id", table_name="ai_thread")
    op.drop_table("ai_thread")
    op.drop_table("video_session")
    op.drop_table("erd_document")
    op.drop_index("ix_workspace_file_version_file_id", table_name="workspace_file_version")
    op.drop_table("workspace_file_version")
    op.drop_index("ix_workspace_file_project_id", table_name="workspace_file")
    op.drop_table("workspace_file")
    op.drop_table("whiteboard_board")
    op.drop_index("ix_chat_message_project_id", table_name="chat_message")
    op.drop_table("chat_message")
