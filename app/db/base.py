"""SQLAlchemy 공통 베이스.

- BigIntPK: MySQL BIGINT / SQLite INTEGER(autoincrement 호환)
- TimestampMixin: created_at / updated_at (UTC 저장)
- SoftDeleteMixin: deleted_at — 세션 이벤트로 `deleted_at IS NULL` 자동 필터
  (우회: session.execute(stmt, execution_options={"include_deleted": True}))
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, Integer, event
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, with_loader_criteria

# SQLite는 INTEGER PRIMARY KEY만 autoincrement 지원
BigIntPK = BigInteger().with_variant(Integer(), "sqlite")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)

    def soft_delete(self) -> None:
        self.deleted_at = utcnow()

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


@event.listens_for(Session, "do_orm_execute")
def _soft_delete_filter(execute_state):
    if (
        execute_state.is_select
        and not execute_state.is_column_load
        and not execute_state.is_relationship_load
        and not execute_state.execution_options.get("include_deleted", False)
    ):
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(
                SoftDeleteMixin,
                lambda cls: cls.deleted_at.is_(None),
                include_aliases=True,
            )
        )
